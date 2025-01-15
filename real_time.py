import requests
import time


class RealTimeDataManager:
    def __init__(self, api_url=None, api_key=None, poll_interval=10):
        """
        :param api_url: Weather or traffic API endpoint
        :param api_key: Key/token to authenticate
        :param poll_interval: Frequency (in seconds) to fetch new data
        """
        self.api_url = api_url
        self.api_key = api_key
        self.poll_interval = poll_interval
        self.latest_data = {}

    def start_polling(self):
        """
        Continuously poll the external API at a fixed interval
        and store data locally. This is a blocking call for simplicity.
        """
        if not self.api_url:
            print("No API URL provided. Skipping real-time data polling.")
            return

        while True:
            try:
                response = requests.get(self.api_url, params={"api_key": self.api_key})
                response.raise_for_status()
                self.latest_data = response.json()
                print("[RealTimeDataManager] Updated weather data:", self.latest_data)
            except Exception as e:
                print("[RealTimeDataManager] Error fetching data:", e)

            time.sleep(self.poll_interval)

    def get_latest(self):
        """
        Provides the most recent polled data.
        """
        return self.latest_data
