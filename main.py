import threading
import uvicorn
from fastapi import FastAPI, Query
from shapely.geometry import Point, box

from data_ingestion import DataIngestionETL
from geoindexing import GeoIndexer
from cost_model import CostModel
from path_planning import PathPlanner
from real_time import RealTimeDataManager

app = FastAPI(
    title="Project AERO",
    description="Dynamic, multi-objective path planning and geo-indexing system (Local Demo).",
    version="1.0.0"
)

# ------------------------------------------------------------------------------
# 1. Initialize Data Ingestion
#    (Load a local GeoJSON of restricted zones for demonstration)
# ------------------------------------------------------------------------------
ingestion = DataIngestionETL(
    vector_path="sample_data/restricted_zones.geojson",  # Adjust path to your local data
    raster_path=None  # optional
)

try:
    restricted_gdf = ingestion.load_vector_data()
except FileNotFoundError:
    restricted_gdf = None
    print("[Warning] Could not load restricted zones. Provide valid geo data if needed.")

# ------------------------------------------------------------------------------
# 2. Geo-Indexing
# ------------------------------------------------------------------------------
if restricted_gdf is not None:
    geo_indexer = GeoIndexer(restricted_gdf)
    geo_indexer.build_spatial_index()
else:
    geo_indexer = None

# ------------------------------------------------------------------------------
# 3. Cost & Risk Model + Path Planner
# ------------------------------------------------------------------------------
cost_model = CostModel(distance_weight=0.4, time_weight=0.3, risk_weight=0.3)
path_planner = PathPlanner(cost_model)

# For demonstration, let’s add some nodes and edges to the path planner's graph
# In a real scenario, you'd generate these nodes from actual geo data (e.g. a route corridor)
path_planner.add_node("PointA", -122.4, 37.7)  # Example coords in SF
path_planner.add_node("PointB", -122.3, 37.8)
path_planner.add_node("PointC", -122.5, 37.9)
# Add edges (dist/time/risk are placeholders)
path_planner.add_edge("PointA", "PointB", distance=1000, time=120, risk_factor=1.0)
path_planner.add_edge("PointB", "PointC", distance=1500, time=180, risk_factor=1.2)
path_planner.add_edge("PointA", "PointC", distance=2000, time=240, risk_factor=1.5)

# ------------------------------------------------------------------------------
# 4. Real-Time Data Integration
# ------------------------------------------------------------------------------
real_time_manager = RealTimeDataManager(
    api_url=None,   # Provide a real API URL if you want to test
    api_key=None,
    poll_interval=20
)
# Optional: Start polling in a background thread if you have a real API
# threading.Thread(target=real_time_manager.start_polling, daemon=True).start()

# ------------------------------------------------------------------------------
# 5. FastAPI Routes
# ------------------------------------------------------------------------------
@app.get("/")
def read_root():
    return {"message": "Welcome to Project AERO (Local Demo)!"}


@app.get("/restricted-zones")
def get_restricted_zones():
    """
    Return the restricted zones as GeoJSON (if loaded).
    """
    if restricted_gdf is None:
        return {"error": "No restricted zones data loaded."}
    return restricted_gdf.__geo_interface__  # GeoJSON-like dict


@app.get("/route")
def get_route(
    start_node: str = Query(..., description="ID of the start node"),
    goal_node: str = Query(..., description="ID of the goal node")
):
    """
    Compute a route using A* between two pre-loaded nodes in the graph.
    """
    path = path_planner.plan_route_a_star(start_node, goal_node)
    if path is None:
        return {"error": f"No path found from {start_node} to {goal_node}."}
    cost = path_planner.get_path_cost(path)
    return {
        "path": path,
        "cost": cost
    }


@app.get("/weather")
def get_latest_weather():
    """
    Example endpoint to show the polled (most recent) weather data.
    """
    return real_time_manager.get_latest()


# ------------------------------------------------------------------------------
# 6. Local Run
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
