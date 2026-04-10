import os
import logging
import subprocess
import sqlite3
import shutil
import joblib
import requests
from datetime import datetime
from flask import Flask, request, jsonify, send_file, render_template, g
from dotenv import load_dotenv
from groq import Groq

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

DB_PATH = "conversations.db"

EMOTION_MODEL = joblib.load("emotion_classifier_pipe_lr_03_june_2021.pkl")

GREETING_KEYWORDS = [
    "hello",
    "hi",
    "hey",
    "good morning",
    "good afternoon",
    "good evening",
    "how are you",
    "what's up",
    "sup",
    "greetings",
]
import re

QUESTION_KEYWORDS = [
    "what",
    "why",
    "how",
    "when",
    "where",
    "who",
    "which",
    "can you",
    "do you",
    "is it",
    "does",
    "could",
    "would",
    "?",
]

UNSAFE_WORDS = [
    "kill",
    "death",
    "die",
    "suicide",
    "hurt",
    "harm",
    "weapon",
    "gun",
    "knife",
    "bomb",
    "attack",
    "violence",
    "blood",
    "abuse",
    "nude",
    "naked",
    "sex",
    "porn",
    "drug",
    "alcohol",
    "cigarette",
    "smoke",
    "drunk",
    "self harm",
    "cut",
    "burn",
    "terrorist",
    "bomb",
    "rape",
    "assault",
    "molest",
]

PROFANITY_WORDS = [
    "shit",
    "fuck",
    "bitch",
    "bastard",
    "asshole",
    "cunt",
    "whore",
    "slut",
    "fucker",
    "fucking",
    "bullshit",
    "dammit",
]

SAFE_RESPONSES = {
    "dangerous": "I'm not able to talk about that. But I'm happy to help you with something else! What would you like to learn about?",
    "inappropriate": "Let's keep our conversation friendly and fun! Is there something else you'd like to talk about?",
    "profanity": "Oops! Let's use nice words. Can we try again?",
}


def check_response_safety(text):
    text_lower = text.lower()

    for word in UNSAFE_WORDS:
        pattern = r"(?<![a-z])" + re.escape(word) + r"(?![a-z])"
        if re.search(pattern, text_lower):
            return False, "dangerous"

    for word in PROFANITY_WORDS:
        pattern = r"(?<![a-z])" + re.escape(word) + r"(?![a-z])"
        if re.search(pattern, text_lower):
            return False, "profanity"

    return True, None


def get_safe_response(flag_type):
    return SAFE_RESPONSES.get(flag_type, SAFE_RESPONSES["inappropriate"])


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        user_message TEXT NOT NULL,
        ai_response TEXT NOT NULL,
        emotion TEXT,
        audio_input TEXT,
        audio_output TEXT,
        flag_type TEXT
    )""")
    try:
        conn.execute("ALTER TABLE conversations ADD COLUMN emotion TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE conversations ADD COLUMN flag_type TEXT")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()


init_db()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
stt_client = Groq(api_key=GROQ_API_KEY)
llm_client = Groq(api_key=GROQ_API_KEY)

ROBOT_PROMPT = """You are a safe, friendly, and intelligent AI assistant designed specifically for children aged 6-14.

Your primary goals are:
1. Help the child learn, explore, and express themselves.
2. Communicate in simple, fun, and engaging way.
3. Detect and respond to the child's emotions (happy, sad, angry, scared, confused, excited, etc.).
4. Encourage positive thinking, curiosity, and emotional growth.

Behavior Rules:
- Always use simple, easy-to-understand language.
- Be warm, supportive, and encouraging like a caring teacher or friend.
- Never use complex jargon unless you explain it simply.
- If the child is sad, scared, or upset -> respond with empathy and comfort.
- If the child is happy or excited -> match their energy and encourage them.
- Ask gentle follow-up questions to understand the child better.
- Never provide harmful, unsafe, or inappropriate content.

Learning Mode:
- Explain concepts using stories, examples, or analogies.
- Turn answers into fun mini-lessons when possible.
- Encourage curiosity by asking "Do you want to try a fun activity?"

Emotion Awareness:
- Analyze the child's message and identify emotion.
- Adjust tone accordingly.
- Provide emotional support if needed.

Memory & Context:
- Remember key things about the child (interests, hobbies, fears).
- Use past conversation context to make responses more personal.

Safety:
- If the child asks something dangerous or inappropriate:
  - Gently refuse
  - Redirect to something safe and educational

Output Style:
- Keep your response to 5 lines maximum
- Friendly tone
- Short to medium responses
- Do NOT use emojis - plain text only
"""


def predict_emotion(text):
    try:
        text_lower = text.lower()
        if any(greet in text_lower for greet in GREETING_KEYWORDS):
            return "neutral"
        if any(q in text_lower for q in QUESTION_KEYWORDS):
            return "neutral"
        result = EMOTION_MODEL.predict([text])[0]
        return result
    except Exception as e:
        print(f"Emotion prediction error: {e}")
        return "neutral"


def detect_emotion_ai(text):
    try:
        emotion_prompt = f"""Analyze the emotion in this message and respond with ONLY ONE word from this list:
happy, sad, angry, scared, confused, excited, neutral

Message: {text}

Respond with just the emotion word, nothing else."""

        completion = llm_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": "You analyze emotions. Respond with exactly one word.",
                },
                {"role": "user", "content": emotion_prompt},
            ],
            temperature=0.3,
            max_completion_tokens=20,
        )

        emotion = completion.choices[0].message.content.strip().lower()

        valid_emotions = [
            "happy",
            "sad",
            "angry",
            "scared",
            "confused",
            "excited",
            "neutral",
        ]
        if emotion in valid_emotions:
            return emotion
        return "neutral"
    except Exception as e:
        print(f"AI emotion detection error: {e}")
        return "neutral"


def generate_tts(text, output_path, voice="female"):
    temp_wav = output_path.replace(".wav", "_temp.wav")
    try:
        data = {"text": text, "voice": voice}
        tts_response = requests.post("http://localhost:8000/tts", data=data, timeout=60)

        if tts_response.status_code == 200:
            with open(temp_wav, "wb") as f:
                f.write(tts_response.content)

            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                temp_wav,
                "-ar",
                "24000",
                "-ac",
                "1",
                "-sample_fmt",
                "s16",
                output_path,
            ]
            result = subprocess.run(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            if result.returncode != 0:
                shutil.copy(temp_wav, output_path)

            if os.path.exists(temp_wav):
                os.remove(temp_wav)
            print(f"TTS: {output_path}")
    except FileNotFoundError:
        if os.path.exists(temp_wav):
            shutil.copy(temp_wav, output_path)
            if os.path.exists(temp_wav):
                os.remove(temp_wav)
            print(f"TTS (no ffmpeg): {output_path}")
    except Exception as e:
        print(f"TTS Error: {e}")


@app.route("/")
def index():
    return render_template("conversations.html")


@app.route("/upload", methods=["POST"])
def upload():
    if "audio" not in request.files:
        return jsonify({"error": "No audio file"}), 400

    audio_file = request.files["audio"]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    voice = request.form.get("voice", "female")

    os.makedirs("mic_input", exist_ok=True)
    os.makedirs("audio_responses", exist_ok=True)

    input_filename = f"mic_input/req_{timestamp}.wav"
    audio_file.save(input_filename)
    print(f"Received: {input_filename}")

    try:
        print("Transcribing...")
        with open(input_filename, "rb") as file:
            transcription = stt_client.audio.transcriptions.create(
                file=("audio.wav", file.read(), "audio/wav"),
                model="whisper-large-v3-turbo",
                response_format="text",
                language="en",
            )

        user_text = str(transcription).strip()
        print(f"User: {user_text}")

        if not user_text:
            return jsonify({"text": "", "ai_response": "Sorry?", "has_audio": False})

        user_safe, user_flag = check_response_safety(user_text)
        warning_note = ""
        flag_type = None
        if not user_safe:
            flag_type = user_flag
            if user_flag == "profanity":
                warning_note = "Note: The child used inappropriate words. Please kindly tell them to use nice words and remind them that bad words are not nice."
            elif user_flag == "dangerous":
                warning_note = "Note: The child mentioned a sensitive topic. Please kindly redirect them to a positive, educational topic."

        emotion = detect_emotion_ai(user_text)
        print(f"Emotion: {emotion}")

        print("Getting AI response...")
        messages = [{"role": "system", "content": ROBOT_PROMPT}]
        db = get_db()
        history = db.execute(
            "SELECT user_message, ai_response FROM conversations ORDER BY id DESC LIMIT 10"
        ).fetchall()
        for row in reversed(history):
            messages.append({"role": "user", "content": row["user_message"]})
            messages.append({"role": "assistant", "content": row["ai_response"]})

        if warning_note:
            messages.append(
                {"role": "user", "content": user_text + "\n\n" + warning_note}
            )
        else:
            messages.append({"role": "user", "content": user_text})

        completion = llm_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=1,
            max_completion_tokens=1024,
            top_p=1,
            stream=False,
        )

        ai_text = completion.choices[0].message.content.strip()
        print(f"AI: {ai_text}")

        is_safe, flag_type = check_response_safety(ai_text)
        if not is_safe:
            ai_text = get_safe_response(flag_type)
            logger.warning(
                f"Unsafe response blocked ({flag_type}) for user input: {user_text[:50]}..."
            )

        output_filename = f"audio_responses/resp_{timestamp}.wav"
        generate_tts(ai_text, output_filename, voice)

        db.execute(
            "INSERT INTO conversations (timestamp, user_message, ai_response, emotion, audio_input, audio_output, flag_type) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                timestamp,
                user_text,
                ai_text,
                emotion,
                input_filename,
                output_filename,
                flag_type,
            ),
        )
        db.commit()

        return jsonify(
            {
                "text": user_text,
                "ai_response": ai_text,
                "emotion": emotion,
                "has_audio": True,
                "audio_url": f"/audio/resp_{timestamp}.wav",
            }
        )

    except Exception as e:
        logger.error(f"Error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/audio/<filename>")
def serve_audio(filename):
    return send_file(f"audio_responses/{filename}", mimetype="audio/wav")


@app.route("/conversations")
def get_conversations():
    limit = request.args.get("limit", 50, type=int)
    db = get_db()
    if limit > 0:
        rows = db.execute(
            "SELECT * FROM conversations ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    else:
        rows = db.execute("SELECT * FROM conversations ORDER BY id DESC").fetchall()
    return jsonify([dict(row) for row in rows])


@app.route("/conversations/<int:conv_id>", methods=["DELETE"])
def delete_conversation(conv_id):
    db = get_db()
    db.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
    db.commit()
    return jsonify({"deleted": conv_id})


@app.route("/conversations/recompute", methods=["POST"])
def recompute_emotions():
    db = get_db()
    rows = db.execute("SELECT id, user_message FROM conversations").fetchall()
    count = 0
    for row in rows:
        emotion = detect_emotion_ai(row["user_message"])
        db.execute(
            "UPDATE conversations SET emotion = ? WHERE id = ?", (emotion, row["id"])
        )
        count += 1
    db.commit()
    return jsonify({"updated": count})


@app.route("/conversations/clear", methods=["POST"])
def clear_conversations():
    db = get_db()
    db.execute("DELETE FROM conversations")
    db.commit()
    return jsonify({"cleared": True})


@app.route("/report")
def report_page():
    return render_template("report.html")


@app.route("/api/report")
def generate_report_api():
    db = get_db()
    rows = db.execute("SELECT * FROM conversations ORDER BY id").fetchall()

    if not rows:
        return jsonify({"message": "No conversations yet"}), 400

    conversation_text = ""
    for row in rows:
        conversation_text += f"User: {row['user_message']}\nAI: {row['ai_response']}\nEmotion: {row['emotion']}\n\n"

    prompt = f"""Create a development report for a child based on their conversation history with an AI assistant. Use ONLY plain text with simple formatting:

1. EMOTIONAL ANALYSIS - (Use heading for each section)
2. TOPIC ANALYSIS
3. DEVELOPMENTAL OBSERVATIONS
4. CONCERNS - Be specific! List exactly what the child said or did that is concerning (include the actual words/messages from the child)
5. RECOMMENDATIONS
6. SUMMARY

Use "Section Name:" format for headings. Use simple bullet points with "- " prefix. Keep it plain text only - NO asterisks, NO markdown.

In CONCERNS section, you MUST include specific examples from the child's actual messages that caused concern (copy the exact words from conversation).

CONVERSATIONS:
{conversation_text}

Generate the report now:"""

    completion = llm_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "system",
                "content": "You are a child development expert. Generate detailed, helpful reports based on conversation analysis.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
        max_completion_tokens=2048,
    )

    report_text = completion.choices[0].message.content.strip()

    return jsonify(
        {
            "report": report_text,
            "total_conversations": len(rows),
        }
    )


if __name__ == "__main__":
    print("Server on port 5050")
    app.run(host="0.0.0.0", port=5050)
