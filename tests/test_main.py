import pytest
import httpx

BASE_URL = "http://127.0.0.1:8000"  # Ensure your FastAPI app is running during the tests

@pytest.fixture(scope="module")
def httpx_client():
    """Provide an HTTPX client for the tests."""
    with httpx.Client(base_url=BASE_URL) as client:
        yield client


def test_index(httpx_client):
    """Test the root endpoint."""
    response = httpx_client.get("/")
    assert response.status_code == 200
    assert response.json()["msg"] == "Single Drone, Single Delivery with consistent lat/lng usage"


def test_create_package(httpx_client):
    """Test the create package endpoint."""
    response = httpx_client.post("/packages/create")
    assert response.status_code == 200
    data = response.json()
    assert "package_id" in data
    assert "lat" in data
    assert "lng" in data


def test_list_packages(httpx_client):
    """Test listing packages."""
    create_response = httpx_client.post("/packages/create")
    assert create_response.status_code == 200
    created_package = create_response.json()

    response = httpx_client.get("/packages")
    assert response.status_code == 200
    packages = response.json()
    assert len(packages) > 0
    package_ids = [pkg["package_id"] for pkg in packages]
    assert created_package["package_id"] in package_ids


def test_list_drones(httpx_client):
    """Test listing drones."""
    response = httpx_client.get("/drones")
    assert response.status_code == 200
    drones = response.json()
    assert len(drones) > 0
    assert "drone_id" in drones[0]
    assert "lat" in drones[0]
    assert "lng" in drones[0]


def test_get_weather(httpx_client):
    """Test the weather endpoint."""
    response = httpx_client.get("/weather")
    assert response.status_code == 200
    weather = response.json()
    assert "weather" in weather
    assert "aqi" in weather


def test_get_elevation(httpx_client):
    """Test the elevation endpoint."""
    lat, lng = 37.7749, -122.4194  # Example coordinates (San Francisco)
    response = httpx_client.get(f"/elevation?lat={lat}&lng={lng}")
    assert response.status_code == 200
    elevation = response.json()
    assert "elevation" in elevation
    assert elevation["lat"] == lat
    assert elevation["lng"] == lng


def test_get_streetview(httpx_client):
    """Test the street view endpoint."""
    lat, lng = 37.7749, -122.4194  # Example coordinates (San Francisco)
    response = httpx_client.get(f"/streetview?lat={lat}&lng={lng}")
    assert response.status_code == 200
    data = response.json()
    assert "streetViewUrl" in data
    assert data["streetViewUrl"].startswith("https://www.google.com/maps")


def test_map_endpoint(httpx_client):
    """Test the map endpoint."""
    response = httpx_client.get("/map")
    assert response.status_code == 200
    assert "<html>" in response.text
