
from flask import Flask, render_template, request, jsonify

from speech.speech_to_text import SpeechToText
from speech.text_to_speech import TextToSpeech
from commands.command_processor import CommandProcessor
from utils.logger import log

app = Flask(__name__)

stt = SpeechToText()
tts = TextToSpeech()
processor = CommandProcessor()


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "message": "Voice Assistant API is running",
        "status": "success"
    })


@app.route("/api/command", methods=["POST"])
def process_command():
    data = request.get_json(silent=True) or {}
    command = data.get("command", "")

    if not isinstance(command, str) or not command.strip():
        return jsonify({
            "error": "Please provide a valid command."
        }), 400

    command = command.strip()
    log(command)

    response = processor.process(command)

    if response == "EXIT":
        response = "Goodbye!"

    # Return the answer to the webpage
    result = jsonify({
        "command": command,
        "response": response
    })

    # Speak the response, preserving your voice assistant
    try:
        tts.speak(response)
    except Exception as error:
        app.logger.error("Text-to-speech error: %s", error)

    return result


if __name__ == "__main__":
    app.run(debug=True)
