import webbrowser
from config.settings import COMMANDS

class Navigation:

    @staticmethod
    def open_website(site):
        if site in COMMANDS:
            webbrowser.open(COMMANDS[site])
            return f"Opening {site}"

        return "Website not configured"