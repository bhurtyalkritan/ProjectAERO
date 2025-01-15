# config.py
import os
from dotenv import load_dotenv

load_dotenv()  # Reads from .env

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")

DRONE_MAX_ELEVATION = 500
CITY_NAME = "San Francisco"
SIMULATION_UPDATE_INTERVAL = 2
DRONE_SPEED_MPS = 10
