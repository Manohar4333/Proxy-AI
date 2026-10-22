import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GROQ_API_KEY")

client = Groq(api_key=api_key) if api_key else None


class CommandProcessor:

    def process(self, command):

        if not command or not command.strip():
            return "Please ask me a question."

        command = command.strip()

        # Exit commands
        if command.lower() in [
            "exit",
            "quit",
            "goodbye",
            "stop assistant"
        ]:
            return "EXIT"

        # Check API configuration
        if client is None:
            return (
                "AI API key is missing. "
                "Please configure GROQ_API_KEY in your .env file."
            )

        try:
            completion = client.chat.completions.create(
                model="openai/gpt-oss-20b",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are Proxy AI, a helpful voice assistant. "
                            "Answer general questions clearly and accurately. "
                            "Keep answers concise and natural for speech. "
                            "If you are uncertain, say so honestly."
                        )
                    },
                    {
                        "role": "user",
                        "content": command
                    }
                ],
                temperature=0.6,
                max_completion_tokens=500
            )

            answer = completion.choices[0].message.content

            return answer or "Sorry, I couldn't generate an answer."

        except Exception as error:
            print(f"AI API error: {error}")
            return (
                "Sorry, I couldn't contact the AI service. "
                "Please try again later."
            )