class CostModel:
    """Computes edge costs using distance, time, and risk."""
    def __init__(self, distance_weight=0.4, time_weight=0.3, risk_weight=0.3):
        self.distance_weight = distance_weight
        self.time_weight = time_weight
        self.risk_weight = risk_weight

    def compute_edge_cost(self, distance, time, risk_factor=1.0):
        """Returns a combined cost for an edge."""
        return (distance * self.distance_weight) + (time * self.time_weight) + (risk_factor * self.risk_weight)
