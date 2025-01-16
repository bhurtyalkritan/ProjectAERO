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
    Creates ONE package within the SF bounding box.
    """
    pid = f"pkg-{random.randint(1000,9999)}-{int(time.time())}"
    lat = random.uniform(BBOX["min_lat"], BBOX["max_lat"])   # e.g. ~37.70 - 37.82
    lng = random.uniform(BBOX["min_lng"], BBOX["max_lng"])   # e.g. ~-122.52 - -122.36

    p = Package(pid, lat, lng)
    packages[pid] = p
    print(f"[create_package] => {pid} at ({lat:.6f}, {lng:.6f})")
    return {"package_id": pid, "lat": lat, "lng": lng}


def assign_package(drone_id: str, package_id: str):
    """
    Drone -> package route (PHASE_DELIVERY).
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

    # NOTE: add_node expects (lng, lat)
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
    route = path_planner.plan_route_a_star(
        start_node=sid,
        goal_node=did,
        drone_id=drone_id,
        conditions=conditions
    )
    if not route:
        pkg.assigned_drone_id = None
        d.current_package_id = None
        d.phase = PHASE_IDLE
        return {"error": f"No feasible route to package {package_id}."}

    pkg.cost = path_planner.get_path_cost(route)

    # The graph stores coords as (lng, lat). We flip them to (lat, lng) for the map.
    coords = []
    for r in route:
        lnglat = path_planner.graph.nodes[r]['coords']  # (lng, lat)
        coords.append((lnglat[1], lnglat[0]))           # => (lat, lng)

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
    End of PHASE_DELIVERY => Mark delivered, then route back to factory (PHASE_RETURN).
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
        lnglat = path_planner.graph.nodes[r]['coords']  # (lng, lat)
        coords_back.append((lnglat[1], lnglat[0]))      # => (lat, lng)

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
    ingestion = DataIngestionETL("sample_data/restricted_zones.geojson")
    gdf = ingestion.load_vector_data()
    if gdf is not None:
        no_fly_indexer = GeoIndexer(gdf)
        no_fly_indexer.build_spatial_index()
        path_planner.geoindexer = no_fly_indexer

    # Single Drone
    drone = Drone("drone-1", FACTORY_LAT, FACTORY_LNG)
    drones.append(drone)
    # Always add node as (lng, lat)
    path_planner.add_node(drone.drone_id, drone.lng, drone.lat)

    path_planner.add_node("factory", FACTORY_LNG, FACTORY_LAT)

    weather_manager.start_polling()

    # Create initial package
    first_pkg = create_package()
    assign_package("drone-1", first_pkg["package_id"])

    scheduler.start(deliver_callback=deliver_internal)
    print("[on_startup] Single drone ready. Created 1 package.")


@app.on_event("shutdown")
def on_shutdown():
    weather_manager.stop_polling()
    scheduler.stop()

@app.get("/")
def index():
    return {
        "msg": "Single Drone, Single Delivery with consistent lat/lng usage",
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


# Weather endpoint
@app.get("/weather")
def get_weather():
    return weather_manager.get_latest()

# Mock/real Elevation endpoint
@app.get("/elevation")
def get_elevation(lat: float, lng: float):
    # Random demo
    elev = 20.0 + random.uniform(-5, 25)
    return {"lat": lat, "lng": lng, "elevation": elev}

# Street View endpoint
@app.get("/streetview")
def get_streetview(lat: float, lng: float):
    url = (
        f"https://www.google.com/maps/embed/v1/streetview"
        f"?key={GOOGLE_MAPS_API_KEY}&location={lat},{lng}&heading=210&pitch=10&fov=80"
    )
    return {"streetViewUrl": url}

# The map with arrow marker + side panel
@app.get("/map")
def serve_map():
    html = f"""
    <!DOCTYPE html>
    <html>
      <head>
        <title>Drone Delivery (Fixed Lat/Lng) with Side Panel</title>
        <style>
          html, body {{
            height: 100%; margin: 0; padding: 0; font-family: Arial, sans-serif;
          }}
          #map {{
            height: 100%; width: 100%;
          }}
          #side-panel {{
            position: absolute;
            right: 0;
            top: 0;
            width: 300px;
            height: 100%;
            background: #f9f9f9;
            border-left: 1px solid #ccc;
            box-sizing: border-box;
            padding: 10px;
            display: none;
          }}
          .info-label {{
            font-weight: bold;
            width: 80px; display: inline-block;
          }}
          #streetview-frame {{
            width: 100%;
            height: 200px;
            border: 1px solid #ccc;
            margin-top: 8px;
          }}
        </style>
        <script src="https://maps.googleapis.com/maps/api/js?key={GOOGLE_MAPS_API_KEY}"></script>
        <script>
          function toRadians(d) {{ return d * Math.PI/180; }}
          function toDegrees(r) {{ return r * 180/Math.PI; }}

          function calcBearing(lat1, lng1, lat2, lng2) {{
            const dLon = toRadians(lng2 - lng1);
            const y = Math.sin(dLon)*Math.cos(toRadians(lat2));
            const x = Math.cos(toRadians(lat1))*Math.sin(toRadians(lat2))
                    - Math.sin(toRadians(lat1))*Math.cos(toRadians(lat2))*Math.cos(dLon);
            const brng = Math.atan2(y, x);
            return (toDegrees(brng) + 360) % 360;
          }}

          let map;
          let droneMarker = null;
          let routeLine = null;
          let packageMarkers = {{}};

          let sidePanel = null;

          async function initMap() {{
            const factory = {{ lat: {FACTORY_LAT}, lng: {FACTORY_LNG} }};
            map = new google.maps.Map(document.getElementById("map"), {{
              center: factory,
              zoom: 12
            }});

            // factory marker
            new google.maps.Marker({{
              position: factory,
              map,
              title: "Factory",
              icon: "http://maps.google.com/mapfiles/ms/icons/blue-dot.png"
            }});

            sidePanel = document.getElementById("side-panel");

            setInterval(updateMap, 1000);
            updateMap();
          }}

          async function updateMap() {{
            try {{
              // Drones
              const drResp = await fetch("/drones");
              const drData = await drResp.json();
              if (drData.length > 0) {{
                const d = drData[0];
                const lat = d.lat;
                const lng = d.lng;
                let bearing = 0;
                if (d.route && d.route.length > 0 && d.next_waypoint_index < d.route.length) {{
                  const nxt = d.route[d.next_waypoint_index];
                  bearing = calcBearing(lat, lng, nxt[0], nxt[1]);
                }}

                if (!droneMarker) {{
                  droneMarker = new google.maps.Marker({{
                    position: {{ lat, lng }},
                    map,
                    icon: {{
                      path: google.maps.SymbolPath.FORWARD_CLOSED_ARROW,
                      scale: 5,
                      rotation: bearing,
                      fillColor: "black",
                      fillOpacity: 1,
                      strokeWeight: 2,
                      strokeColor: "white"
                    }},
                    title: "Drone"
                  }});
                  droneMarker.addListener("click", () => {{
                    openSidePanel(lat, lng);
                  }});
                }} else {{
                  droneMarker.setPosition({{ lat, lng }});
                  droneMarker.setIcon({{
                    path: google.maps.SymbolPath.FORWARD_CLOSED_ARROW,
                    scale: 5,
                    rotation: bearing,
                    fillColor: "black",
                    fillOpacity: 1,
                    strokeWeight: 2,
                    strokeColor: "white"
                  }});
                }}

                // route
                if (d.route && d.route.length > 0) {{
                  const coords = d.route.map(pt => {{return {{ lat: pt[0], lng: pt[1]}}}});
                  if (!routeLine) {{
                    routeLine = new google.maps.Polyline({{
                      path: coords,
                      geodesic: true,
                      strokeColor: "#FF0000",
                      strokeOpacity: 1.0,
                      strokeWeight: 3,
                      map
                    }});
                  }} else {{
                    routeLine.setPath(coords);
                  }}
                }} else if (routeLine) {{
                  routeLine.setMap(null);
                  routeLine = null;
                }}
              }}

              // Packages
              const pkgResp = await fetch("/packages");
              const pkgData = await pkgResp.json();
              pkgData.forEach(pkg => {{
                const lat = pkg.destination[0];
                const lng = pkg.destination[1];
                if (!pkg.delivered) {{
                  if (!packageMarkers[pkg.package_id]) {{
                    const marker = new google.maps.Marker({{
                      position: {{ lat, lng }},
                      map,
                      icon: "http://maps.google.com/mapfiles/ms/icons/red-dot.png",
                      title: "Package " + pkg.package_id
                    }});
                    marker.addListener("click", () => {{
                      openSidePanel(lat, lng);
                    }});
                    packageMarkers[pkg.package_id] = marker;
                  }}
                }} else if (packageMarkers[pkg.package_id]) {{
                  packageMarkers[pkg.package_id].setMap(null);
                  delete packageMarkers[pkg.package_id];
                }}
              }});

            }} catch(err) {{
              console.error("updateMap error:", err);
            }}
          }}

          async function openSidePanel(lat, lng) {{
            sidePanel.style.display = "block";
            document.getElementById("info-lat").textContent = lat.toFixed(6);
            document.getElementById("info-lng").textContent = lng.toFixed(6);

            // Weather
            try {{
              const wResp = await fetch("/weather");
              const wData = await wResp.json();
              let wMain = "N/A", temp = "N/A", aqi = "N/A";
              if (wData.weather && wData.weather.weather) {{
                wMain = wData.weather.weather[0].main;
                temp = wData.weather.main.temp + "°C";
              }}
              if (wData.aqi) {{
                aqi = "AQI=" + wData.aqi;
              }}
              document.getElementById("info-weather").textContent = wMain + " / " + temp + " / " + aqi;
            }} catch(e) {{
              document.getElementById("info-weather").textContent = "Err";
            }}

            // Elevation
            try {{
              const elevUrl = `/elevation?lat=${'{'}lat{'}'}&lng=${'{'}lng{'}'}`;
              const elevResp = await fetch(elevUrl);
              if (elevResp.ok) {{
                const elevData = await elevResp.json();
                const val = elevData.elevation ? elevData.elevation.toFixed(2) + " m" : "N/A";
                document.getElementById("info-elev").textContent = val;
              }} else {{
                document.getElementById("info-elev").textContent = "N/A";
              }}
            }} catch(ex) {{
              document.getElementById("info-elev").textContent = "N/A";
            }}

            // Street View
            try {{
              const svUrl = `/streetview?lat=${'{'}lat{'}'}&lng=${'{'}lng{'}'}`;
              const svResp = await fetch(svUrl);
              if (svResp.ok) {{
                const svData = await svResp.json();
                if (svData.streetViewUrl) {{
                  document.getElementById("streetview-frame").src = svData.streetViewUrl;
                }} else {{
                  document.getElementById("streetview-frame").src = "";
                }}
              }}
            }} catch(ex) {{
              document.getElementById("streetview-frame").src = "";
            }}
          }}
        </script>
      </head>
      <body onload="initMap()">
        <div id="map"></div>
        <div id="side-panel">
          <h2>Location Info</h2>
          <div>
            <span class="info-label">Latitude:</span> <span id="info-lat">-</span>
          </div>
          <div>
            <span class="info-label">Longitude:</span> <span id="info-lng">-</span>
          </div>
          <div>
            <span class="info-label">Weather:</span> <span id="info-weather">-</span>
          </div>
          <div>
            <span class="info-label">Elevation:</span> <span id="info-elev">-</span>
          </div>
          <h3>Street View</h3>
          <iframe id="streetview-frame"></iframe>
        </div>
      </body>
    </html>
    """
    return Response(content=html, media_type="text/html")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
