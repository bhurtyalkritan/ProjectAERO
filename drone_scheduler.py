import threading
import time
import math
from config import SIMULATION_UPDATE_INTERVAL, DRONE_SPEED_MPS

class DroneScheduler:
    """
    Simulates drone movement along assigned routes.
    """
    def __init__(self, drones):
        self.drones = drones
        self.running = False
        self.thread = None
        self.deliver_callback = None

    def start(self, deliver_callback):
        """Starts the background simulation thread."""
        if self.running:
            return
        self.running = True
        self.deliver_callback = deliver_callback
        self.thread = threading.Thread(target=self._update_loop, daemon=True)
        self.thread.start()

    def stop(self):
        """Stops the background simulation."""
        self.running = False

    def _update_loop(self):
        while self.running:
            self._update_drones()
            time.sleep(SIMULATION_UPDATE_INTERVAL)

    def _update_drones(self):
        for d in self.drones:
            if d.route and d.next_waypoint_index < len(d.route):
                d.is_moving = True
                curr_lat, curr_lng = d.lat, d.lng
                next_lat, next_lng = d.route[d.next_waypoint_index]
                dist = self._distance(curr_lat, curr_lng, next_lat, next_lng)
                step = DRONE_SPEED_MPS * SIMULATION_UPDATE_INTERVAL
                if dist <= step:
                    d.lat, d.lng = next_lat, next_lng
                    d.next_waypoint_index += 1
                    if d.next_waypoint_index >= len(d.route):
                        d.is_moving = False
                        if self.deliver_callback:
                            self.deliver_callback(d.drone_id)
                else:
                    ratio = step / dist
                    d.lat += (next_lat - curr_lat) * ratio
                    d.lng += (next_lng - curr_lng) * ratio

    def _distance(self, lat1, lng1, lat2, lng2):
        return math.dist((lat1, lng1), (lat2, lng2))
