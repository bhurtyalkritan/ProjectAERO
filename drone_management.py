class Package:
    """Tracks a package with ID, destination, assigned drone, times, and status."""
    def __init__(self, package_id, lat, lng):
        self.package_id = package_id
        self.lat = lat
        self.lng = lng
        self.assigned_drone_id = None
        self.delivered = False
        self.start_time = None
        self.end_time = None
        self.cost = None
        self.outcome = None

class Drone:
    """Represents a drone with location, route, assigned package, and movement state."""
    def __init__(self, drone_id, lat, lng):
        self.drone_id = drone_id
        self.lat = lat
        self.lng = lng
        self.route = []
        self.current_package_id = None
        self.is_moving = False
        self.next_waypoint_index = 0
