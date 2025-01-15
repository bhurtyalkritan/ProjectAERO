import math

class CostModel:
    def __init__(self, distance_weight=0.4, time_weight=0.3, risk_weight=0.3):
        """
        :param distance_weight: weighting factor for distance
        :param time_weight: weighting factor for time
        :param risk_weight: weighting factor for risk
        """
        self.distance_weight = distance_weight
        self.time_weight = time_weight
        self.risk_weight = risk_weight

    def compute_edge_cost(self, distance, estimated_time, risk_factor=1.0):
        """
        Compute a single cost value from distance, time, and risk factor.
        You can adapt or expand this to incorporate other domain-specific data.

        :param distance: distance in meters/kilometers
        :param estimated_time: flight time in seconds or minutes
        :param risk_factor: a multiplier that increases with no-fly zones, weather severity, etc.
        :return: a single numeric cost
        """
        cost_dist = distance * self.distance_weight
        cost_time = estimated_time * self.time_weight
        cost_risk = risk_factor * self.risk_weight
        return cost_dist + cost_time + cost_risk

    def compute_weather_penalty(self, weather_data):
        """
        Example function to convert weather conditions into a risk factor.
        For instance, if wind speed is high or storms are in the area,
        increase the risk factor.
        """
        wind_speed = weather_data.get("wind_speed", 0)
        if wind_speed < 5:
            return 1.0
        elif 5 <= wind_speed < 15:
            return 1.5
        else:
            return 2.0

    def compute_elevation_penalty(self, elevation_diff):
        """
        Example function to add cost based on elevation changes.
        """
        if elevation_diff < 20:  # minor changes
            return 1.0
        elif 20 <= elevation_diff < 100:
            return 1.2
        else:
            return 1.5
