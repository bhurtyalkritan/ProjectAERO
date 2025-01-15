import networkx as nx
from shapely.geometry import Point
from cost_model import CostModel

class PathPlanner:
    def __init__(self, cost_model: CostModel):
        self.graph = nx.Graph()
        self.cost_model = cost_model

    def add_node(self, node_id, x, y, elevation=0):
        """
        Add a node to the graph with coordinates and optional elevation.
        """
        self.graph.add_node(node_id, coords=(x, y), elevation=elevation)

    def add_edge(self, node_a, node_b, distance, time, risk_factor=1.0):
        """
        Add an edge between two nodes with a computed cost using the cost model.
        """
        cost = self.cost_model.compute_edge_cost(distance, time, risk_factor)
        self.graph.add_edge(node_a, node_b, weight=cost, distance=distance,
                            time=time, risk_factor=risk_factor)

    def plan_route_a_star(self, start_node, goal_node):
        """
        Compute the least-cost path using A* search.
        We'll define a heuristic as the direct distance (straight-line)
        between nodes, or 0 if we want uniform-cost search.
        """

        def heuristic(u, v):
            # Use Euclidean distance as a heuristic
            x1, y1 = self.graph.nodes[u]['coords']
            x2, y2 = self.graph.nodes[v]['coords']
            return ((x1 - x2) ** 2 + (y1 - y2) ** 2) ** 0.5

        try:
            path = nx.astar_path(self.graph, start_node, goal_node,
                                 heuristic=heuristic, weight='weight')
            return path
        except nx.NetworkXNoPath:
            return None

    def get_path_cost(self, path):
        """
        Sum up the edge weights along the path.
        """
        if not path or len(path) < 2:
            return float('inf')
        total_cost = 0
        for i in range(len(path) - 1):
            edge_data = self.graph.get_edge_data(path[i], path[i+1])
            total_cost += edge_data.get('weight', 0)
        return total_cost
