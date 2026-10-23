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
