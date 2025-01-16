import threading
import time
import math
from math import sin, cos, sqrt, atan2, radians

from drone_management import PHASE_IDLE, PHASE_DELIVERY, PHASE_RETURN

SIMULATION_UPDATE_INTERVAL = 2
DRONE_SPEED_MPS = 10

class DroneScheduler:
    """
    Moves a single drone (or multiple, but here we keep it simple)
    in two phases: DELIVERY (factory->package), then RETURN (package->factory).
    Once back at factory, we create a new package only once.
    """
    def __init__(
        self,
        drones,
        create_package_func,
        assign_package_func,
        factory_lat,
        factory_lng
    ):
        self.drones = drones
        self.create_package_func = create_package_func
        self.assign_package_func = assign_package_func
        self.factory_lat = factory_lat
        self.factory_lng = factory_lng

        self.running = False
        self.thread = None
        self.deliver_callback = None

    def start(self, deliver_callback=None):
        """
        Starts the background update thread.
        deliver_callback: function for end-of-delivery (PHASE_DELIVERY).
        """
        if self.running:
            return
        self.running = True
        self.deliver_callback = deliver_callback
        self.thread = threading.Thread(target=self._update_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()

    def _update_loop(self):
        while self.running:
            self._update_drones()
            time.sleep(SIMULATION_UPDATE_INTERVAL)

    def _update_drones(self):
        """
        Moves the drone step by step.
        PHASE_DELIVERY -> calls deliver_callback.
        PHASE_RETURN   -> once drone reaches factory, create a new package and assign it.
        """
        for drone in self.drones:
            if not drone.is_moving or not drone.route:
                continue

            if drone.next_waypoint_index >= len(drone.route):
                # Completed current route
                if drone.phase == PHASE_DELIVERY and self.deliver_callback:
                    self.deliver_callback(drone.drone_id)
                elif drone.phase == PHASE_RETURN:
                    # Arrived factory -> create new package, assign to drone
                    drone.phase = PHASE_IDLE
                    drone.is_moving = False
                    drone.next_waypoint_index = 0
                    drone.route = []
                    self._create_and_assign_package(drone)
                continue

            # Move toward next waypoint
            next_lat, next_lng = drone.route[drone.next_waypoint_index]
            dist = self._haversine_distance(drone.lat, drone.lng, next_lat, next_lng)
            step = DRONE_SPEED_MPS * SIMULATION_UPDATE_INTERVAL

            if dist <= step:
                # Reached waypoint
                drone.lat = next_lat
                drone.lng = next_lng
                drone.next_waypoint_index += 1
            else:
                fraction = step / dist
                drone.lat, drone.lng = self._interpolate_position(
                    drone.lat, drone.lng,
                    next_lat, next_lng,
                    fraction
                )

    def _create_and_assign_package(self, drone):
        """
        Called after the drone returns to factory.
        Creates a new package, assigns it => PHASE_DELIVERY.
        """
        new_pkg_info = self.create_package_func()
        resp = self.assign_package_func(drone.drone_id, new_pkg_info["package_id"])
        if "error" not in resp:
            drone.phase = PHASE_DELIVERY

    def _haversine_distance(self, lat1, lon1, lat2, lon2):
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
        c = 2*atan2(sqrt(a), sqrt(1-a))
        r = 6371000
        return r*c

    def _interpolate_position(self, lat1, lng1, lat2, lng2, fraction):
        lat = lat1 + (lat2 - lat1)*fraction
        lng = lng1 + (lng2 - lng1)*fraction
        return lat, lng
