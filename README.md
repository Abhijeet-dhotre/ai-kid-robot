# AI Chat Robot for Children

A child-friendly AI voice assistant that combines an ESP32-S3 robot with a Flask server for voice conversation, emotion detection, and text-to-speech synthesis.

## Features

- 🎤 Voice recording and transcription (Whisper STT)
- 🤖 AI conversation with Groq Llama model
- 😊 Emotion detection
- 🔊 Text-to-speech (Microsoft Edge TTS)
- 🤖 ESP32-S3 robot with OLED eyes
- 💾 Conversation history storage (SQLite)
- 📊 Child development reports

## Architecture

```
[ESP32 Robot] --(audio)--> [Flask Server] --(API)--> [Groq: Whisper + Llama]
                              |
                              +-> [TTS Server] --(audio)--> [ESP32 Robot]
                              |
                              +-> [SQLite DB]
```
<img width="883" height="558" alt="image" src="https://github.com/user-attachments/assets/d388c389-7005-49d7-9b41-0bcab3eff7fd" />

## Hardware

- ESP32-S3 (XIAO)
- Microphone (I2S)
- Speaker (I2S)
- OLED Display (128x64)
- Push button

![WhatsApp Image 2026-04-03 at 07 33 38](https://github.com/user-attachments/assets/3361600c-ab27-488d-9ba7-c9d36f08a97c)


## Prerequisites

- Python 3.8+
- ffmpeg
- ESP32 Arduino board

## Installation

1. Install Python dependencies:
```bash
pip install flask flask-cors joblib requests groq python-dotenv edge-tts
```

2. Configure API key in `.env`:
```
GROQ_API_KEY=your_api_key_here
```

3. Run servers:
```bash
# Terminal 1 - TTS Server
python tts_server.py

# Terminal 2 - Main Server
python server.py
```

Or use the batch file:
```bash
run_server.bat
```

## Usage

1. Hold the button on ESP32 robot to start recording
2. Speak your message
3. Release button to send
4. Robot will play AI response and show emotion on OLED eyes

## Web Interface

- Conversations: http://localhost:5050/
- Reports: http://localhost:5050/report

## Endpoints

| Endpoint | Method | Description |
|---------|--------|------------|
| `/upload` | POST | Upload audio, get AI response |
| `/audio/` | GET | Get response audio |
| `/conversations` | GET | Get conversation history |
| `/conversations/<id>` | DELETE | Delete conversation |
| `/conversations/clear` | POST | Clear all conversations |
| `/conversations/recompute` | POST | Recompute emotions |
| `/report` | GET | View report page |
| `/api/report` | GET | Generate report |

## Technologies

- **STT:** Whisper-large-v3-turbo (Groq)
- **LLM:** Llama-3.3-70b-versatile (Groq)
- **TTS:** Microsoft Edge TTS
- **Emotion:** TF-IDF + Logistic Regression
- **Web:** Flask + HTML/CSS

## License

MIT
