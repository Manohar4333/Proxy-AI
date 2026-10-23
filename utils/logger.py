from datetime import datetime

def log(message):

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open("assistant.log", "a") as file:
        file.write(f"[{timestamp}] {message}\n")