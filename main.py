# main.py

import uvicorn
import random
import math
import time
from typing import Optional
from fastapi import FastAPI, Response

from config import (
    GOOGLE_MAPS_API_KEY, OPENWEATHER_API_KEY, CITY_NAME,
    DRONE_MAX_ELEVATION, SIMULATION_UPDATE_INTERVAL,
    DRONE_SPEED_MPS
)
from data_ingestion import DataIngestionETL
from geoindexing import GeoIndexer
from cost_model import CostModel
from google_maps_helper import GoogleMapsHelper
from real_time import RealTimeDataManager
from machine_learning import DroneMLManager
from path_planning import PathPlanner
from drone_management import Drone, Package, PHASE_IDLE, PHASE_DELIVERY, PHASE_RETURN
from drone_scheduler import DroneScheduler

app = FastAPI(title="Single Drone Delivery Demo", version="1.0.0")

# Globals
no_fly_indexer = None
weather_manager = RealTimeDataManager(city=CITY_NAME, api_key=OPENWEATHER_API_KEY)
ml_manager = DroneMLManager()
maps_helper = GoogleMapsHelper(api_key=GOOGLE_MAPS_API_KEY)
cost_model = CostModel()
path_planner = PathPlanner(cost_model, geoindexer=None, maps_helper=maps_helper, ml_manager=ml_manager)

drones = []
packages = {}

# SINGLE Drone
FACTORY_LAT = 37.644249
FACTORY_LNG = -122.401533

BBOX = {
    "min_lat": 37.70,
    "max_lat": 37.82,
    "min_lng": -122.52,
    "max_lng": -122.36
}

scheduler = DroneScheduler(
    drones=drones,
    create_package_func=lambda: create_package(),
    assign_package_func=lambda d_id, p_id: assign_package(d_id, p_id),
    factory_lat=FACTORY_LAT,
    factory_lng=FACTORY_LNG
)


@app.post("/packages/create")
def create_package():
    """
    Creates ONE package in the bounding box.
    Called by the scheduler after the drone returns to factory.
    """
    pid = f"pkg-{random.randint(1000,9999)}-{int(time.time())}"
    lat = random.uniform(BBOX["min_lat"], BBOX["max_lat"])
    lng = random.uniform(BBOX["min_lng"], BBOX["max_lng"])
    p = Package(pid, lat, lng)
    packages[pid] = p
    print(f"[create_package] => {pid} at ({lat:.6f}, {lng:.6f})")
    return {"package_id": pid, "lat": lat, "lng": lng}


def assign_package(drone_id: str, package_id: str):
    """
    Assign route: drone -> package (PHASE_DELIVERY).
    """
    d = next((x for x in drones if x.drone_id == drone_id), None)
    if not d:
        return {"error": f"No drone {drone_id}"}

    pkg = packages.get(package_id)
    if not pkg:
        return {"error": f"No package {package_id}"}
    if pkg.delivered:
        return {"error": f"Package {package_id} is delivered."}

    pkg.assigned_drone_id = drone_id
    d.current_package_id = package_id
    pkg.start_time = time.time()
    d.phase = PHASE_DELIVERY

    # Build route in path_planner
    sid = f"{drone_id}_pos"
    path_planner.add_node(sid, d.lng, d.lat)
    did = f"dest_{package_id}"
    path_planner.add_node(did, pkg.lng, pkg.lat)
    dist_f = math.dist((d.lng, d.lat), (pkg.lng, pkg.lat))
    path_planner.add_edge(sid, did, dist_f, dist_f, 1.0)

    conditions = {
        "weather": weather_manager.get_latest()
            .get("weather", {})
            .get("weather", [{}])[0]
            .get("main", ""),
        "elev_range": "unknown"
    }
    route = path_planner.plan_route_a_star(sid, did, drone_id=drone_id, conditions=conditions)

    if not route:
        pkg.assigned_drone_id = None
        d.current_package_id = None
        d.phase = PHASE_IDLE
        return {"error": f"No feasible route to package {package_id}."}

    pkg.cost = path_planner.get_path_cost(route)

    coords = []
    for r in route:
        c = path_planner.graph.nodes[r]['coords']
        coords.append((c[1], c[0]))

    d.route = coords
    d.is_moving = True
    d.next_waypoint_index = 0

    print(f"[assign_package] Drone {drone_id} => {package_id}, route len={len(coords)}")
    return {
        "drone_id": drone_id,
        "package_id": package_id,
        "cost": pkg.cost,
        "coords": coords
    }


def deliver_internal(drone_id: str):
    """
    Called at end of PHASE_DELIVERY:
    Mark package delivered, route drone PHASE_RETURN => factory.
    """
    d = next((x for x in drones if x.drone_id == drone_id), None)
    if not d:
        return {"error": f"No drone {drone_id}"}
    if not d.current_package_id:
        return {"error": f"Drone {drone_id} has no package assigned."}

    pkg = packages[d.current_package_id]
    pkg.delivered = True
    pkg.end_time = time.time()
    pkg.outcome = "success"

    ml_manager.update_experience(
        drone_id=drone_id,
        outcome="success",
        conditions={"weather": "?", "elev_range": "?"},
        cost_incurred=pkg.cost if pkg.cost else 1000
    )
    old_pkg = d.current_package_id
    d.current_package_id = None
    d.phase = PHASE_RETURN

    print(f"[deliver_internal] Drone {drone_id} delivered {old_pkg}, returning to factory")

    # Route => factory
    sid = f"{drone_id}_return_pos"
    path_planner.add_node(sid, d.lng, d.lat)
    dist_f = math.dist((d.lng, d.lat), (FACTORY_LAT, FACTORY_LNG))
    path_planner.add_edge(sid, "factory", dist_f, dist_f, 1.0)

    route_back = path_planner.plan_route_a_star(
        start_node=sid,
        goal_node="factory",
        drone_id=drone_id,
        conditions={"weather": "?", "elev_range": "?"}
    )
    if not route_back:
        d.is_moving = False
        d.route = []
        d.next_waypoint_index = 0
        d.phase = PHASE_IDLE
        return {"message": f"No route back to factory from {d.lat:.6f},{d.lng:.6f}"}

    coords_back = []
    for r in route_back:
        c = path_planner.graph.nodes[r]['coords']
        coords_back.append((c[1], c[0]))

    d.route = coords_back
    d.is_moving = True
    d.next_waypoint_index = 0

    return {
        "message": f"Delivered {old_pkg}, returning now...",
        "route_back": coords_back
    }


@app.on_event("startup")
def on_startup():
    global no_fly_indexer
    # optional no-fly zones
    ingestion = DataIngestionETL("sample_data/restricted_zones.geojson")
    gdf = ingestion.load_vector_data()
    if gdf is not None:
        no_fly_indexer = GeoIndexer(gdf)
        no_fly_indexer.build_spatial_index()
        path_planner.geoindexer = no_fly_indexer

    # Single Drone
    drone = Drone("drone-1", FACTORY_LAT, FACTORY_LNG)
    drones.append(drone)
    path_planner.add_node(drone.drone_id, drone.lng, drone.lat)

    # factory node
    path_planner.add_node("factory", FACTORY_LNG, FACTORY_LAT)

    # start weather manager
    weather_manager.start_polling()

    # create an initial package so there's something to deliver
    initial_pkg = create_package()
    assign_package("drone-1", initial_pkg["package_id"])

    # start scheduler
    scheduler.start(deliver_callback=deliver_internal)
    print("[on_startup] Single drone ready. Created 1 package.")


@app.on_event("shutdown")
def on_shutdown():
    weather_manager.stop_polling()
    scheduler.stop()


@app.get("/")
def index():
    return {
        "msg": "Single Drone, Single Delivery at a Time",
        "drone_speed": DRONE_SPEED_MPS,
        "interval": SIMULATION_UPDATE_INTERVAL
    }


@app.get("/drones")
def list_drones():
    return [
        {
            "drone_id": d.drone_id,
            "lat": d.lat,
            "lng": d.lng,
            "phase": d.phase,
            "route": d.route,
            "current_package_id": d.current_package_id
        }
        for d in drones
    ]


@app.get("/packages")
def list_packages():
    return [
        {
            "package_id": p.package_id,
            "destination": (p.lat, p.lng),
            "assigned_drone_id": p.assigned_drone_id,
            "delivered": p.delivered,
            "start_time": p.start_time,
            "end_time": p.end_time,
            "cost": p.cost,
            "outcome": p.outcome
        }
        for p in packages.values()
    ]


@app.get("/map")
def serve_map():
    html = f"""
    <!DOCTYPE html>
    <html>
      <head>
        <title>Single Drone Delivery</title>
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
              zoom: 12
            }});

            new google.maps.Marker({{
              position: factory,
              map: map,
              title: "Factory",
              icon: "http://maps.google.com/mapfiles/ms/icons/blue-dot.png"
            }});

            let droneMarker = null;
            let routeLine = null;
            let packageMarkers = {{}};

            async function update() {{
              try {{
                const dronesResp = await fetch("/drones");
                const dronesData = await dronesResp.json();
                if (dronesData.length > 0) {{
                  const d = dronesData[0];
                  // Update drone marker
                  const pos = {{ lat: d.lat, lng: d.lng }};
                  if (!droneMarker) {{
                    droneMarker = new google.maps.Marker({{
                      position: pos,
                      map,
                      title: "Drone"
                    }});
                  }} else {{
                    droneMarker.setPosition(pos);
                  }}

                  // If route is defined, draw it
                  if (d.route && d.route.length > 0) {{
                    const path = d.route.map(pt => {{ return {{ lat: pt[0], lng: pt[1] }}; }});
                    if (!routeLine) {{
                      routeLine = new google.maps.Polyline({{
                        path,
                        geodesic: true,
                        strokeColor: '#FF0000',
                        strokeOpacity: 1.0,
                        strokeWeight: 3,
                        map
                      }});
                    }} else {{
                      routeLine.setPath(path);
                    }}
                  }} else if (routeLine) {{
                    routeLine.setMap(null);
                    routeLine = null;
                  }}
                }}

                // Packages
                const pkgResp = await fetch("/packages");
                const pkgData = await pkgResp.json();
                // clear old markers if the package is delivered
                pkgData.forEach(pkg => {{
                  if (!pkg.delivered) {{
                    if (!packageMarkers[pkg.package_id]) {{
                      packageMarkers[pkg.package_id] = new google.maps.Marker({{
                        position: {{ lat: pkg.destination[0], lng: pkg.destination[1] }},
                        map,
                        icon: "http://maps.google.com/mapfiles/ms/icons/red-dot.png",
                        title: "Package " + pkg.package_id
                      }});
                    }}
                  }} else if (packageMarkers[pkg.package_id]) {{
                    packageMarkers[pkg.package_id].setMap(null);
                    delete packageMarkers[pkg.package_id];
                  }}
                }});
              }} catch(err) {{
                console.error(err);
              }}
            }}

            setInterval(update, 1000);
            update();
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
