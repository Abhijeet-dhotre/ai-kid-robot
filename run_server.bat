@echo off
echo Starting Robot Server...

start "Pocket TTS" cmd /k "uvx pocket-tts serve"

timeout /t 3 /nobreak >nul
start "" "http://127.0.0.1:5050"

python server.py

pause
