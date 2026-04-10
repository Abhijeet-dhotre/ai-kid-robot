import os
import io
import logging
import asyncio
from flask import Flask, request, send_file
import edge_tts

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

VOICE_MAP = {
    "female": "en-US-JennyNeural",
    "male": "en-US-GuyNeural",
    "default": "en-US-JennyNeural",
}


async def generate_speech(text, voice="female"):
    voice_name = VOICE_MAP.get(voice, VOICE_MAP["default"])

    communicate = edge_tts.Communicate(text, voice_name)

    audio_buffer = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_buffer.write(chunk["data"])

    audio_buffer.seek(0)
    return audio_buffer


@app.route("/tts", methods=["POST"])
def tts():
    try:
        text = request.form.get("text", "")
        voice = request.form.get("voice", "female")

        if not text:
            return "No text provided", 400

        logger.info(f"TTS request: voice={voice}, text={text[:50]}...")

        audio_buffer = asyncio.run(generate_speech(text, voice))

        return send_file(audio_buffer, mimetype="audio/wav", as_attachment=False)

    except Exception as e:
        logger.error(f"TTS error: {e}")
        return str(e), 500


if __name__ == "__main__":
    print("TTS Server running on http://localhost:8000")
    print("Using Microsoft Edge TTS (free)")
    app.run(host="0.0.0.0", port=8000)
