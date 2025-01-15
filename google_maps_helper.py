import requests

class GoogleMapsHelper:
    """Fetches elevation data from Google Elevation API."""
    def __init__(self, api_key):
        self.api_key = api_key

    def get_elevation(self, lat, lng):
        """Returns elevation in meters."""
        url = "https://maps.googleapis.com/maps/api/elevation/json"
        params = {"locations": f"{lat},{lng}", "key": self.api_key}
        resp = requests.get(url, params=params).json()
        results = resp.get("results", [])
        if results:
            return results[0].get("elevation", 0)
        return 0
