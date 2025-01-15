import requests
import time
import threading

class RealTimeDataManager:
    """Manages real-time weather and air quality for a given city."""
    def __init__(self, city, api_key, poll_interval=60):
        self.city = city
        self.api_key = api_key
        self.poll_interval = poll_interval
        self.latest_data = {}
        self._running = False
        self._thread = None

    def start_polling(self):
        """Starts background polling."""
        if not self.api_key:
            return
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def _poll_loop(self):
        while self._running:
            try:
                self.latest_data = self._fetch_weather_and_aqi()
            except Exception:
                pass
            time.sleep(self.poll_interval)

    def _fetch_weather_and_aqi(self):
        """Fetches weather and AQI from OpenWeatherMap."""
        url = "http://api.openweathermap.org/data/2.5/weather"
        params = {"q": self.city, "appid": self.api_key, "units": "metric"}
        weather_resp = requests.get(url, params=params).json()
        lat = weather_resp.get("coord", {}).get("lat")
        lon = weather_resp.get("coord", {}).get("lon")
        aqi_data = None
        if lat and lon:
            aqi_url = "http://api.openweathermap.org/data/2.5/air_pollution"
            aqi_params = {"lat": lat, "lon": lon, "appid": self.api_key}
            aqi_resp = requests.get(aqi_url, params=aqi_params).json()
            if "list" in aqi_resp and len(aqi_resp["list"]) > 0:
                aqi_data = aqi_resp["list"][0]["main"].get("aqi")
        return {"weather": weather_resp, "aqi": aqi_data}

    def stop_polling(self):
        """Stops polling."""
        self._running = False

    def get_latest(self):
        """Returns the latest polled data."""
        return self.latest_data
