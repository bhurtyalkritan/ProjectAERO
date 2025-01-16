# machine_learning.py
import random

class DroneMLManager:
    """
    Uses a Q-learning approach to adjust drone risk factors
    based on conditions (weather, elevation range) and outcomes.
    """
    def __init__(self, alpha=0.3, gamma=0.9):
        self.alpha = alpha
        self.gamma = gamma
        self.q_table = {}  # Q[(drone_id, weather, elev_range)] = Q-value

    def get_state_key(self, drone_id, conditions):
        """Returns a state key based on drone, weather, elevation range."""
        w = conditions.get("weather", None)
        e = conditions.get("elev_range", None)
        return (drone_id, w, e)

    def get_risk_factor(self, drone_id, conditions):
        """Returns a derived risk factor from Q-value."""
        state = self.get_state_key(drone_id, conditions)
        q_val = self.q_table.get(state, 1.0)
        noise = random.uniform(-0.05, 0.05)
        return max(0.1, q_val + noise)

    def update_experience(self, drone_id, outcome, conditions, cost_incurred):
        """
        Updates Q-value based on outcome (success/fail), cost, and discounting.
        A success yields a reward inversely related to cost.
        A failure yields a negative reward.
        """
        state = self.get_state_key(drone_id, conditions)
        old_q = self.q_table.get(state, 1.0)

        if outcome == "success":
            reward = max(1, 2000 / (cost_incurred + 1))  # bigger reward if cost is small
        else:
            reward = -50

        new_q = (1 - self.alpha) * old_q + self.alpha * (reward + self.gamma * 0)
        self.q_table[state] = new_q
