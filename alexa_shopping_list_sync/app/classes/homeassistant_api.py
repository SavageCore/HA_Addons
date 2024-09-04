import requests


class HomeAssistantAPI:

    def __init__(self, url, token, logger=None):
        if url.startswith("wss"):
            self.url = url.replace("wss", "https", 1)
        elif url.startswith("ws"):
            self.url = url.replace("ws", "http", 1)
        self.url = self.url.replace("websocket", "config", 1)
        self.token = token
        self.logger = logger

    def get_current_language(self):
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        response = requests.get(f"{self.url}", headers=headers)
        response.raise_for_status()  # Raise an exception for HTTP errors
        config_data = response.json()
        return config_data.get("language", "en-GB")  # Default to 'en' if not found
