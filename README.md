Drone Delivery Application

This project is a FastAPI-based simulation of a single-drone delivery system. The application handles package creation, drone routing, real-time data integration, and delivery tracking with a visually interactive map and side panel.

Features

Package Management:

Create packages within a defined bounding box.

Assign packages to a drone for delivery.

Drone Management:

Monitor drone status, including location, delivery phase, and route.

Handle delivery phases: idle, delivery, and return.

Routing and Cost Modeling:

Plan routes using A* algorithm with real-time conditions (e.g., weather).

Estimate delivery costs dynamically.

Real-Time Data Integration:

Weather data from OpenWeather API.

Elevation and street view data for map enrichment.

Interactive Map Interface:

Display drone and package locations.

Show routes and real-time information on click.

Prerequisites

Ensure you have the following installed:

Python 3.9+

Docker

Docker Compose (optional for simplified container management)

APIs and Keys

You need API keys for:

Google Maps API (for street view and maps)

OpenWeather API (for real-time weather data)

Create a .env file in the root directory:

GOOGLE_MAPS_API_KEY=your_google_maps_api_key
OPENWEATHER_API_KEY=your_openweather_api_key
CITY_NAME=San Francisco
DRONE_MAX_ELEVATION=120
SIMULATION_UPDATE_INTERVAL=5
DRONE_SPEED_MPS=10

Installation

Clone the repository:

git clone https://github.com/yourusername/drone-delivery-app.git
cd drone-delivery-app

Install dependencies:

pip install -r requirements.txt

Run the application:

uvicorn main:app --host 127.0.0.1 --port 8000

Access the application:

Open your browser and navigate to http://127.0.0.1:8000.

Using Docker

Build and Run the Image

Build the Docker image:

docker build -t drone-delivery-app .

Run the container:

docker run -d -p 8000:8000 --env-file .env drone-delivery-app

Access the application:

Open your browser and navigate to http://127.0.0.1:8000.

Docker Compose (Optional)

Use docker-compose for simplified setup:

Create a docker-compose.yml file:

version: '3.8'
services:
  app:
    build: .
    ports:
      - "8000:8000"
    env_file:
      - .env

Start the application:

docker-compose up

Stop the application:

docker-compose down

Endpoints

General Endpoints

GET / - Root endpoint providing metadata about the application.

GET /drones - List all drones and their statuses.

GET /packages - List all packages and their statuses.

Package Management

POST /packages/create - Create a new package within the bounding box.

Weather and Map Data

GET /weather - Retrieve real-time weather data.

GET /elevation?lat={lat}&lng={lng} - Get elevation data for a location.

GET /streetview?lat={lat}&lng={lng} - Get Google Street View URL for a location.

GET /map - Serve an interactive map interface.

File Structure

.
├── main.py                  # FastAPI application entry point
├── requirements.txt         # Python dependencies
├── Dockerfile               # Docker configuration
├── .dockerignore            # Files to exclude from Docker build
├── .env                     # Environment variables (not included in Docker image)
├── config.py                # Configuration settings
├── data_ingestion.py        # Handles data ingestion for restricted zones
├── geoindexing.py           # Handles geospatial indexing
├── cost_model.py            # Cost estimation logic
├── google_maps_helper.py    # Helper for Google Maps API interactions
├── real_time.py             # Manages real-time data like weather
├── machine_learning.py      # Machine learning-based route optimization
├── path_planning.py         # Path planning using A* algorithm
├── drone_management.py      # Drone and package management
├── drone_scheduler.py       # Scheduler for managing drone tasks
└── sample_data/             # Sample data for restricted zones

