import uvicorn
import random
import math
import time
from typing import Optional
from fastapi import FastAPI, Response

from config import GOOGLE_MAPS_API_KEY, OPENWEATHER_API_KEY, CITY_NAME
from data_ingestion import DataIngestionETL
from geoindexing import GeoIndexer
from cost_model import CostModel
from google_maps_helper import GoogleMapsHelper
from real_time import RealTimeDataManager
from machine_learning import DroneMLManager
from path_planning import PathPlanner
from drone_management import Drone, Package
from drone_scheduler import DroneScheduler

app = FastAPI(title="Complex Drone Delivery with ML & Simulation", version="2.0.0")

# Global variables and instances
no_fly_indexer = None
weather_manager = RealTimeDataManager(city=CITY_NAME, api_key=OPENWEATHER_API_KEY)
ml_manager = DroneMLManager()
maps_helper = GoogleMapsHelper(api_key=GOOGLE_MAPS_API_KEY)
cost_model = CostModel()
path_planner = PathPlanner(cost_model, geoindexer=None, maps_helper=maps_helper, ml_manager=ml_manager)
drones = []
packages = {}

scheduler = DroneScheduler(drones)

FACTORY_LAT = 37.644249  # Starting latitude
FACTORY_LNG = -122.401533  # Starting longitude
BBOX = {"min_lat": 37.7, "max_lat": 37.82, "min_lng": -122.52, "max_lng": -122.36}


def deliver_internal(drone_id: str):
    """
    Shared delivery logic used by both the DroneScheduler and the /deliver endpoint.
    Marks the package as delivered, updates times, resets drone state, and reassigns.
    """
    d = next((x for x in drones if x.drone_id == drone_id), None)
    if not d:
        return {"error": "Drone not found"}

    if not d.current_package_id:
        return {"message": "No package assigned"}

    pkg = packages[d.current_package_id]
    pkg.delivered = True
    pkg.end_time = time.time()
    pkg.outcome = "success"

    # Update ML experience
    conditions = {"weather": "?", "elev_range": "?"}
    ml_manager.update_experience(drone_id, "success", conditions, pkg.cost if pkg.cost else 1000)

    # Reset drone state
    d.current_package_id = None
    d.route = []
    d.is_moving = False
    d.next_waypoint_index = 0

    # Optionally assign a new package automatically
    resp = assign_package(drone_id)
    return {
        "delivered_package": pkg.package_id,
        "new_delivery": resp,
        "drone_location": (d.lat, d.lng)
    }


@app.on_event("startup")
def on_startup():
    global no_fly_indexer
    ingestion = DataIngestionETL("sample_data/restricted_zones.geojson")
    gdf = ingestion.load_vector_data()
    if gdf is not None:
        no_fly_indexer = GeoIndexer(gdf)
        no_fly_indexer.build_spatial_index()
        path_planner.geoindexer = no_fly_indexer

    # Create some drones
    for i in range(2):
        d = Drone(f"drone-{i + 1}", FACTORY_LAT, FACTORY_LNG)
        drones.append(d)
        nid = d.drone_id
        path_planner.add_node(nid, d.lng, d.lat)

    # Example nodes/edges in the path_planner
    path_planner.add_node("factory", FACTORY_LNG, FACTORY_LAT)
    path_planner.add_edge("drone-1", "factory", 1000, 100, 1.0)
    path_planner.add_edge("drone-2", "factory", 800, 90, 1.1)

    # Start up any background tasks
    weather_manager.start_polling()

    # Start the drone scheduler, passing our internal delivery function
    scheduler.start(deliver_callback=deliver_internal)


@app.on_event("shutdown")
def on_shutdown():
    weather_manager.stop_polling()
    scheduler.stop()


@app.get("/")
def home():
    return {"message": "Drone Delivery with ML & Movement Simulation"}


@app.get("/weather")
def get_weather():
    return weather_manager.get_latest()


@app.get("/drones")
def list_drones():
    out = []
    for d in drones:
        out.append({
            "drone_id": d.drone_id,
            "lat": d.lat,
            "lng": d.lng,
            "route": d.route,
            "current_package_id": d.current_package_id,
            "is_moving": d.is_moving,
            "next_waypoint_index": d.next_waypoint_index
        })
    return out


@app.get("/packages")
def list_packages():
    """
    Return details of all packages in the system.
    """
    return [{
        "package_id": p.package_id,
        "destination": (p.lat, p.lng),
        "assigned_drone_id": p.assigned_drone_id,
        "delivered": p.delivered,
        "start_time": p.start_time,
        "end_time": p.end_time,
        "cost": p.cost,
        "outcome": p.outcome
    } for p in packages.values()]


@app.get("/deliveries/status")
def deliveries_status():
    """
    Returns a comprehensive table of all deliveries (packages).
    """
    table = []
    for p in packages.values():
        table.append({
            "package_id": p.package_id,
            "assigned_drone_id": p.assigned_drone_id,
            "delivered": p.delivered,
            "start_time": p.start_time,
            "end_time": p.end_time,
            "cost": p.cost,
            "outcome": p.outcome
        })
    return table


@app.post("/packages/create")
def create_package():
    """
    Randomly create a new package within a bounding box.
    """
    pid = f"pkg-{random.randint(1000, 9999)}-{int(time.time())}"
    lat = random.uniform(BBOX["min_lat"], BBOX["max_lat"])
    lng = random.uniform(BBOX["min_lng"], BBOX["max_lng"])
    p = Package(pid, lat, lng)
    packages[pid] = p
    return {"package_id": pid, "lat": lat, "lng": lng}


@app.post("/assign")
def assign_package(drone_id: str, package_id: Optional[str] = None):
    """
    Assign an existing or new package to a drone and plan its route.
    """
    d = next((x for x in drones if x.drone_id == drone_id), None)
    if not d:
        return {"error": "Drone not found"}

    # Create a new package if not provided
    if package_id is None:
        resp = create_package()
        package_id = resp["package_id"]

    pkg = packages.get(package_id)
    if not pkg:
        return {"error": "Package not found"}

    # If the package is already assigned and not yet delivered
    if pkg.assigned_drone_id and not pkg.delivered:
        return {"error": "Package already assigned"}

    # Mark assignment
    pkg.assigned_drone_id = drone_id
    d.current_package_id = package_id
    pkg.start_time = time.time()

    # Add nodes for current drone position & destination
    sid = f"{drone_id}_pos"
    path_planner.add_node(sid, d.lng, d.lat)
    did = f"dest_{package_id}"
    path_planner.add_node(did, pkg.lng, pkg.lat)
    dist_f = math.dist((d.lng, d.lat), (pkg.lng, pkg.lat))
    path_planner.add_edge(sid, did, dist_f, dist_f, 1.0)

    # Gather conditions for route planning
    conditions = {
        "weather": weather_manager.get_latest().get("weather", {}).get("weather", [{}])[0].get("main", ""),
        "elev_range": "unknown"
    }
    route = path_planner.plan_route_a_star(sid, did, drone_id=drone_id, conditions=conditions)
    if not route:
        pkg.assigned_drone_id = None
        d.current_package_id = None
        return {"error": "No feasible route"}

    # Calculate cost, update package
    total_cost = path_planner.get_path_cost(route)
    pkg.cost = total_cost

    # Convert route node coords to (lat, lng) pairs
    coords = []
    for r in route:
        c = path_planner.graph.nodes[r]['coords']
        coords.append((c[1], c[0]))

    # Update drone route
    d.route = coords
    d.is_moving = True
    d.next_waypoint_index = 0

    return {
        "drone_id": drone_id,
        "package_id": package_id,
        "route": route,
        "cost": total_cost
    }


@app.post("/deliver")
def deliver(drone_id: str):
    """
    Endpoint to handle package delivery.
    Calls our internal deliver function.
    """
    return deliver_internal(drone_id)


@app.get("/map")
def serve_map():
    """
    Serve an interactive map showing drones, the factory, and delivery points.
    Updates periodically to reflect real-time data.
    """
    html = f"""
    <!DOCTYPE html>
    <html>
      <head>
        <title>Drone Delivery Map</title>
        <style>
          html, body {{ height: 100%; margin: 0; padding: 0; }}
          #map {{ height: 100%; width: 100%; }}
        </style>
        <script src="https://maps.googleapis.com/maps/api/js?key={GOOGLE_MAPS_API_KEY}"></script>
        <script>
          async function initMap() {{
            const factory = {{ lat: {FACTORY_LAT}, lng: {FACTORY_LNG} }};
            const map = new google.maps.Map(document.getElementById('map'), {{
              center: factory,
              zoom: 12,
              mapTypeId: 'roadmap'
            }});

            // Add a marker for the factory (start point)
            const factoryMarker = new google.maps.Marker({{
              position: factory,
              map: map,
              title: "Factory - Start Point",
              icon: "http://maps.google.com/mapfiles/ms/icons/blue-dot.png"
            }});

            // Arrays to hold markers for drones and deliveries
            let droneMarkers = [];
            let deliveryMarkers = [];

            // Function to update drones and delivery markers
            async function updateMap() {{
              try {{
                // Fetch drone data
                const droneResponse = await fetch('/drones');
                const drones = await droneResponse.json();

                // Fetch delivery data
                const deliveryResponse = await fetch('/deliveries/status');
                const deliveries = await deliveryResponse.json();

                // Clear existing markers
                droneMarkers.forEach(marker => marker.setMap(null));
                deliveryMarkers.forEach(marker => marker.setMap(null));
                droneMarkers = [];
                deliveryMarkers = [];

                // Add new drone markers
                drones.forEach(drone => {{
                  const marker = new google.maps.Marker({{
                    position: {{ lat: drone.lat, lng: drone.lng }},
                    map: map,
                    title: `Drone ID: ${'{'}drone.drone_id{'}'}`
                  }});
                  droneMarkers.push(marker);
                }});

                // Add new delivery markers
                deliveries.forEach(delivery => {{
                  if (!delivery.delivered) {{
                    const marker = new google.maps.Marker({{
                      position: {{ lat: delivery.destination[0], lng: delivery.destination[1] }},
                      map: map,
                      title: `Delivery ID: ${'{'}delivery.package_id{'}'}`,
                      icon: "http://maps.google.com/mapfiles/ms/icons/red-dot.png"
                    }});
                    deliveryMarkers.push(marker);
                  }}
                }});
              }} catch (error) {{
                console.error("Error updating map:", error);
              }}
            }}

            // Update the map every 3 seconds
            setInterval(updateMap, 3000);
            await updateMap();
          }}
        </script>
      </head>
      <body onload="initMap()">
        <div id="map"></div>
      </body>
    </html>
    """
    return Response(content=html, media_type="text/html")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
