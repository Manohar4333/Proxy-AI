<<<<<<< HEAD
# Project_Proxy_AI
Python AI Interview model on Voice interaction between client and AI where it works as an HR to ask questions just like an interview process.

## Run the interview app

Question generation is served by Flask; do not open `template/interview.html` directly from the file system.

1. Install the Python dependencies:

   ```powershell
   python -m pip install -r requirements.txt
   ```

2. Start Ollama and make the configured model available:

   ```powershell
   ollama pull qwen2.5:1.5b
   ```

3. Start Flask from the project root:

   ```powershell
   python Python\app.py
   ```

4. Open [http://127.0.0.1:5000](http://127.0.0.1:5000). Enter a job role and comma-separated skills to generate a shuffled mix of 10 role/skills, 5 HR, 5 project, and 5 casual questions. The technical questions have two at each of five levels, and the project questions have one at each level. Generation may take a few minutes on a local model.
=======
# Proxy AI

Proxy AI is a small Python and Flask voice-assistant web app. Ask a question by typing it into the browser or, where supported, by using your browser's microphone. The app sends the command to the Groq chat API, displays the reply, and attempts to read it aloud using `pyttsx3`.

## Features

- Web interface for submitting text commands
- Optional browser-based speech recognition
- AI-generated replies through Groq
- Text-to-speech playback on the machine running Flask
- Health-check and command API endpoints

## Requirements

- Python 3.10 or later
- A Groq API key for AI-generated replies
- A modern browser; microphone input requires browser speech-recognition support and microphone permission

## Setup

Open a terminal in the project directory and create a virtual environment:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install the packages used by the application:

```powershell
python -m pip install Flask groq python-dotenv pyttsx3 SpeechRecognition
```

Create a `.env` file in the project root and add your Groq API key:

```dotenv
GROQ_API_KEY=your_groq_api_key
```

Keep the key private and do not commit the `.env` file. Without a key, the web app can still start, but requests will receive a message explaining that the key is missing.

## Run

Start the Flask development server:

```powershell
python main.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser. Allow microphone access if you want to use voice input. Browser speech recognition is not available in every browser and may require a secure context; `localhost` is generally treated as secure.

To stop the server, press `Ctrl+C` in the terminal.

## API

### `GET /api/health`

Returns a JSON status response to indicate that the Flask app is running.

### `POST /api/command`

Submit a command as JSON:

```json
{
  "command": "Tell me a short joke"
}
```

A successful response contains the submitted command and assistant reply:

```json
{
  "command": "Tell me a short joke",
  "response": "..."
}
```

An empty or invalid command returns HTTP `400` with an error message.

## Project structure

```text
.
├── commands/
│   ├── command_processor.py  # Sends prompts to Groq and handles exit phrases
│   └── navigation.py         # Opens configured websites
├── config/
│   └── settings.py           # Assistant name and configured website URLs
├── frontend/                 # Separate static login-page assets
├── speech/
│   ├── speech_to_text.py     # Python microphone speech-recognition helper
│   └── text_to_speech.py     # pyttsx3 speech output
├── templates/
│   └── index.html            # Main assistant web interface
├── utils/
│   └── logger.py             # Appends submitted commands to assistant.log
└── main.py                   # Flask app and API routes
```

## Notes

- The main page uses the browser's speech-recognition API for microphone input. The Python `SpeechToText` helper is separate and is not used by the current web route.
- Speech output is performed by the Flask process, so audio plays on the machine running the server.
- `assistant.log` records submitted commands. Avoid entering sensitive information.
- The app starts Flask with debug mode enabled for local development. Do not expose the development server to an untrusted network or use it as a production server.
- `frontend/login.html` is a standalone static page; authentication is not connected to the Flask application.
>>>>>>> c112379261b0a663f6289ea233f6051d88b5e602
