# path_planning.py
import math
import networkx as nx
from shapely.geometry import Point
from config import DRONE_MAX_ELEVATION

class PathPlanner:
    """Performs A* routing with optional no-fly zone checks and elevation limits."""
    def __init__(self, cost_model, geoindexer=None, maps_helper=None, ml_manager=None):
        self.graph = nx.Graph()
        self.cost_model = cost_model
        self.geoindexer = geoindexer
        self.maps_helper = maps_helper
        self.ml_manager = ml_manager

    def add_node(self, node_id, lng, lat):
        self.graph.add_node(node_id, coords=(lng, lat))

    def add_edge(self, node_a, node_b, distance, time, base_risk=1.0):
        c = self.cost_model.compute_edge_cost(distance, time, base_risk)
        self.graph.add_edge(node_a, node_b, weight=c,
                            distance=distance, time=time,
                            base_risk=base_risk)

    def plan_route_a_star(self, start_node, goal_node, drone_id=None, conditions=None):
        if conditions is None:
            conditions = {}
        if self.ml_manager and drone_id:
            ml_risk_factor = self.ml_manager.get_risk_factor(drone_id, conditions)
        else:
            ml_risk_factor = 1.0

        # A* heuristic: Euclidean distance between nodes
        def heuristic(u, v):
            (lng1, lat1) = self.graph.nodes[u]['coords']
            (lng2, lat2) = self.graph.nodes[v]['coords']
            return math.dist((lng1, lat1), (lng2, lat2))

        # Adjust edges by ML risk factor
        for (u, v, data) in self.graph.edges(data=True):
            base = data["weight"]
            self.graph[u][v]["weight"] = base * ml_risk_factor

        try:
            path = nx.astar_path(
                self.graph, start_node, goal_node,
                heuristic=heuristic, weight="weight"
            )
            if not self._check_path_constraints(path):
                return None
            return path
        except nx.NetworkXNoPath:
            return None

    def _check_path_constraints(self, path):
        """Check no-fly zones and elevation constraints."""
        for node in path:
            lng, lat = self.graph.nodes[node]['coords']
            pt = Point(lng, lat)

            # No-fly zone check
            if self.geoindexer:
                hits = self.geoindexer.query(pt.buffer(0.0001))
                for _, row in hits.iterrows():
                    if row.geometry.intersects(pt):
                        return False

            # Elevation check
            if self.maps_helper:
                elev = self.maps_helper.get_elevation(lat, lng)
                if elev > DRONE_MAX_ELEVATION:
                    return False
        return True

    def get_path_cost(self, path):
        if not path or len(path) < 2:
            return float("inf")
        total = 0
        for i in range(len(path) - 1):
            data = self.graph[path[i]][path[i + 1]]
            total += data["weight"]
        return total
