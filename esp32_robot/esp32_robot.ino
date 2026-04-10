#include <HTTPClient.h>
#include <driver/i2s.h>
#include <ArduinoJson.h>
#include <WiFiManager.h>
#include <WiFi.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include "RoboEyesSimple.h"

WiFiManager wifiManager;

#define OLED_SDA    3
#define OLED_SCL    44
#define OLED_WIDTH  128
#define OLED_HEIGHT 64

Adafruit_SSD1306 display(OLED_WIDTH, OLED_HEIGHT, &Wire, -1);
RoboEyesSimple<Adafruit_SSD1306> eyes(display);

bool isPlayingAudio = false;
unsigned long audioEndTime = 0;
bool currentMood = DEFAULT;

#define BUTTON_PIN 2
#define LED_PIN 21

#define MIC_I2S_WS  4
#define MIC_I2S_SCK 5
#define MIC_I2S_SD  6

#define AMP_I2S_LRC 7
#define AMP_I2S_BCLK 8
#define AMP_I2S_DIN 43
#define AMP_ENABLE 1

#define SAMPLE_RATE     24000
#define MIC_SAMPLE_RATE 16000
#define RECORD_SECONDS  3
#define SAMPLE_SIZE     2
#define BUFFER_SIZE     (MIC_SAMPLE_RATE * RECORD_SECONDS * SAMPLE_SIZE)

uint8_t *audio_buffer;
bool lastButtonState = HIGH;
bool recording = false;
int recording_position = 0;

const char* WIFI_SSID_FALLBACK = "AXR";
const char* WIFI_PASS_FALLBACK = "@bhijeet";
String server_url = "http://10.83.57.94:5050";

void setup() {
  Serial.begin(115200);
  delay(1000);

  pinMode(BUTTON_PIN, INPUT_PULLUP);
  pinMode(LED_PIN, OUTPUT);
  pinMode(AMP_ENABLE, OUTPUT);
  digitalWrite(AMP_ENABLE, HIGH);
  digitalWrite(LED_PIN, LOW);

  Serial.println("XIAO ESP32-S3 Robot Starting...");

  Wire.begin(OLED_SDA, OLED_SCL);
  if(!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println("OLED init failed!");
    while(1);
  }
  Serial.println("OLED initialized");

  eyes.begin(OLED_WIDTH, OLED_HEIGHT, 50);
  eyes.setAutoblinker(true, 3, 2);
  eyes.setMood(DEFAULT);
  eyes.update();

  audio_buffer = (uint8_t*)ps_malloc(BUFFER_SIZE);
  if(audio_buffer == NULL) audio_buffer = (uint8_t*)malloc(BUFFER_SIZE);

  if(audio_buffer == NULL) {
    Serial.println("CRITICAL: Not enough RAM!");
    while(1) delay(100);
  }
  Serial.printf("Audio Buffer: %d bytes\n", BUFFER_SIZE);

  connectToWiFi();
  setupMicrophoneI2S();
  
  xTaskCreatePinnedToCore(animationTask, "anim", 4096, NULL, 1, NULL, 1);
  
  Serial.println("Setup Complete. Press and HOLD button to talk.");
}

void loop() {
  bool currentButtonState = digitalRead(BUTTON_PIN);

  if (lastButtonState == HIGH && currentButtonState == LOW) {
    delay(50);
    if (digitalRead(BUTTON_PIN) == LOW) startRecording();
  }

  if (lastButtonState == LOW && currentButtonState == HIGH) {
    delay(50);
    if (recording) stopRecordingAndProcess();
  }

  if (recording) recordAudioData();
  lastButtonState = currentButtonState;
  delay(10);
}

void animationTask(void* parameter) {
  while (true) {
    if (isPlayingAudio && millis() < audioEndTime) {
      eyes.setMood(HAPPY);
    } else {
      isPlayingAudio = false;
      eyes.setMood(currentMood);
    }
    eyes.update();
    delay(20);
  }
}

void connectToWiFi() {
  WiFi.mode(WIFI_STA);
  Serial.println("Connecting...");
  wifiManager.setTimeout(180);

  if(!wifiManager.autoConnect("XIAO-Robot-Setup")) {
    Serial.println("Using fallback credentials...");
    WiFi.begin(WIFI_SSID_FALLBACK, WIFI_PASS_FALLBACK);
    delay(5000);
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("IP: "); Serial.println(WiFi.localIP());
  }
}

void setupMicrophoneI2S() {
  i2s_driver_uninstall(I2S_NUM_0);
  delay(20);

  i2s_config_t i2s_config = {
    .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
    .sample_rate = MIC_SAMPLE_RATE,
    .bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT,
    .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
    .communication_format = I2S_COMM_FORMAT_STAND_I2S,
    .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count = 8,
    .dma_buf_len = 256,
    .use_apll = false,
    .tx_desc_auto_clear = false,
    .fixed_mclk = 0
  };

  i2s_pin_config_t pin_config = {
    .bck_io_num = MIC_I2S_SCK,
    .ws_io_num = MIC_I2S_WS,
    .data_out_num = I2S_PIN_NO_CHANGE,
    .data_in_num = MIC_I2S_SD
  };

  i2s_driver_install(I2S_NUM_0, &i2s_config, 0, NULL);
  i2s_set_pin(I2S_NUM_0, &pin_config);
  i2s_zero_dma_buffer(I2S_NUM_0);
}

void startRecording() {
  recording = true;
  recording_position = 0;
  digitalWrite(LED_PIN, HIGH);
  Serial.println("Recording...");
}

void recordAudioData() {
  if (!recording) return;
  size_t bytes_read = 0;

  if (recording_position < BUFFER_SIZE) {
    int read_size = min(512, BUFFER_SIZE - recording_position);
    i2s_read(I2S_NUM_0, audio_buffer + recording_position, read_size, &bytes_read, portMAX_DELAY);
    recording_position += bytes_read;

    if (recording_position >= BUFFER_SIZE) {
      Serial.println("Buffer Full");
      stopRecordingAndProcess();
    }
  }
}

void stopRecordingAndProcess() {
  recording = false;
  digitalWrite(LED_PIN, LOW);
  Serial.printf("Recorded %d bytes\n", recording_position);

  int16_t* samples = (int16_t*)audio_buffer;
  int sample_count = recording_position / 2;
  for (int i = 0; i < sample_count; i++) {
    int32_t val = samples[i] * 2;
    if (val > 32767) val = 32767;
    if (val < -32768) val = -32768;
    samples[i] = (int16_t)val;
  }

  sendAudioStreamed(recording_position);
}

void sendAudioStreamed(int data_size) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("No WiFi");
    return;
  }

  WiFiClient client;
  String host = server_url;
  host.replace("http://", "");
  int split = host.indexOf(':');
  String ip = host.substring(0, split);
  int port = host.substring(split + 1).toInt();

  if (!client.connect(ip.c_str(), port)) {
    Serial.println("Connection Failed");
    return;
  }

  client.setTimeout(30000);

  uint8_t wav_header[44];
  createWavHeader(wav_header, data_size, MIC_SAMPLE_RATE);

  String boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW";
  String head = "--" + boundary + "\r\nContent-Disposition: form-data; name=\"audio\"; filename=\"xiao.wav\"\r\nContent-Type: audio/wav\r\n\r\n";
  String tail = "\r\n--" + boundary + "--\r\n";

  int totalLength = head.length() + 44 + data_size + tail.length();

  client.println("POST /upload HTTP/1.1");
  client.print("Host: "); client.println(ip);
  client.println("Content-Type: multipart/form-data; boundary=" + boundary);
  client.print("Content-Length: "); client.println(totalLength);
  client.println("Connection: close");
  client.println();

  client.print(head);
  client.write(wav_header, 44);

  int sent = 0;
  while(sent < data_size) {
    int chunk = min(1024, data_size - sent);
    client.write(audio_buffer + sent, chunk);
    sent += chunk;
  }

  client.print(tail);

  Serial.println("Waiting for response...");

  String response = "";
  bool body_started = false;

  while(client.connected() || client.available()) {
    String line = client.readStringUntil('\n');
    if(line == "\r") body_started = true;
    else if(body_started) response += line;
  }
  client.stop();

  int jsonStart = response.indexOf('{');
  int jsonEnd = response.lastIndexOf('}');

  if(jsonStart != -1) {
    String cleanJson = response.substring(jsonStart, jsonEnd + 1);
    DynamicJsonDocument doc(4096);
    DeserializationError error = deserializeJson(doc, cleanJson);

    if (!error) {
      String aiText = doc["ai_response"].as<String>();
      Serial.println("AI: " + aiText);

      if (doc.containsKey("emotion")) {
        String emotion = doc["emotion"].as<String>();
        Serial.println("Emotion: " + emotion);
        
        if (emotion == "happy" || emotion == "excited") {
          currentMood = HAPPY;
        } else if (emotion == "sad") {
          currentMood = TIRED;
        } else if (emotion == "angry") {
          currentMood = ANGRY;
        } else {
          currentMood = DEFAULT;
        }
      }

      if (doc["has_audio"]) {
        String audioPath = doc["audio_url"].as<String>();
        audioPath.replace("//", "/");
        String full_url = server_url + audioPath;
        Serial.println("Playing: " + full_url);
        
        playAudioURL(full_url);
      }
    } else {
      Serial.print("JSON Error: "); Serial.println(error.c_str());
    }
  }

  eyes.setMood(currentMood);
  eyes.update();
  setupMicrophoneI2S();
}

void setupSpeakerI2S(int rate) {
  i2s_driver_uninstall(I2S_NUM_0);
  delay(20);

  i2s_config_t i2s_config = {
    .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_TX),
    .sample_rate = (uint32_t)rate,
    .bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT,
    .channel_format = I2S_CHANNEL_FMT_RIGHT_LEFT,
    .communication_format = I2S_COMM_FORMAT_STAND_I2S,
    .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count = 8,
    .dma_buf_len = 256,
    .use_apll = false,
    .tx_desc_auto_clear = true,
    .fixed_mclk = 0
  };

  i2s_pin_config_t pin_config = {
    .bck_io_num = AMP_I2S_BCLK,
    .ws_io_num = AMP_I2S_LRC,
    .data_out_num = AMP_I2S_DIN,
    .data_in_num = I2S_PIN_NO_CHANGE
  };

  i2s_driver_install(I2S_NUM_0, &i2s_config, 0, NULL);
  i2s_set_pin(I2S_NUM_0, &pin_config);
  i2s_zero_dma_buffer(I2S_NUM_0);
}

unsigned long calculateAudioDuration(int sizeBytes, int sampleRate) {
  int dataSize = sizeBytes - 44;
  int bytesPerSample = 2;
  int samples = dataSize / bytesPerSample;
  unsigned long durationMs = (unsigned long)samples * 1000 / sampleRate;
  return durationMs;
}

void playAudioURL(String url) {
  Serial.println("Playing audio from: " + url);

  HTTPClient http;
  WiFiClient client;

  if (http.begin(client, url)) {
    int httpCode = http.GET();
    Serial.printf("HTTP Code: %d\n", httpCode);

    if (httpCode == 200) {
      int len = http.getSize();
      Serial.printf("Content-Length: %d\n", len);

      if (len > 44) {
        WiFiClient* stream = http.getStreamPtr();

        uint8_t header[44];
        stream->readBytes(header, 44);

        if (header[0] == 'R' && header[1] == 'I' && header[2] == 'F' && header[3] == 'F') {
          uint32_t sampleRate = header[24] | (header[25] << 8) | (header[26] << 16) | (header[27] << 24);
          Serial.printf("Sample Rate: %d Hz\n", sampleRate);
          
          unsigned long durationMs = calculateAudioDuration(len, sampleRate);
          Serial.printf("Audio duration: %lu ms\n", durationMs);
          isPlayingAudio = true;
          audioEndTime = millis() + durationMs + 500;

          setupSpeakerI2S(sampleRate);

          int remaining = len - 44;
          uint8_t buff[512];
          int16_t stereo[512];

          while (remaining > 0) {
            int toRead = min(512, remaining);
            int bytesRead = stream->readBytes(buff, toRead);

            if (bytesRead > 0) {
              int samples = bytesRead / 2;
              int16_t* mono = (int16_t*)buff;

              for (int i = 0; i < samples; i++) {
                stereo[i * 2] = mono[i];
                stereo[i * 2 + 1] = mono[i];
              }

              size_t written;
              i2s_write(I2S_NUM_0, stereo, samples * 4, &written, 100);
              remaining -= bytesRead;
            } else {
              break;
            }
          }
          Serial.println("Playback Complete!");
        } else {
          Serial.println("Invalid WAV file");
        }
      } else {
        Serial.println("File too small");
      }
    }
  }
  http.end();
}

void createWavHeader(uint8_t* header, int waveDataSize, int sampleRate) {
  int fileSize = waveDataSize + 36;
  memcpy(header, "RIFF", 4);
  *(int32_t*)(header + 4) = fileSize;
  memcpy(header + 8, "WAVEfmt ", 8);
  *(int32_t*)(header + 16) = 16;
  *(int16_t*)(header + 20) = 1;
  *(int16_t*)(header + 22) = 1;
  *(int32_t*)(header + 24) = sampleRate;
  *(int32_t*)(header + 28) = sampleRate * 2;
  *(int16_t*)(header + 32) = 2;
  *(int16_t*)(header + 34) = 16;
  memcpy(header + 36, "data", 4);
  *(int32_t*)(header + 40) = waveDataSize;
}