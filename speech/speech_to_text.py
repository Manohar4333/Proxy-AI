import speech_recognition as sr

class SpeechToText:

    def __init__(self):
        self.recognizer = sr.Recognizer()

    def listen(self):
        with sr.Microphone() as source:
            print("Listening...")
            self.recognizer.adjust_for_ambient_noise(source)

            audio = self.recognizer.listen(source)

        try:
            text = self.recognizer.recognize_google(audio)
            print(f"User: {text}")
            return text.lower()

        except sr.UnknownValueError:
            return ""

        except sr.RequestError:
            print("Speech service unavailable")
            return ""