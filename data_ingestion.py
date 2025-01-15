

import geopandas as gpd
import rasterio
import requests
import os


class DataIngestionETL:
    def __init__(self, vector_path=None, raster_path=None):
        """
        :param vector_path: path to local vector data (e.g., shapefile, GeoJSON)
        :param raster_path: path to local raster data (e.g., DEM)
        """
        self.vector_path = vector_path
        self.raster_path = raster_path

        # These will store data in memory after loading
        self.vector_data = None
        self.raster_meta = None

    def load_vector_data(self, crs="EPSG:4326"):
        """Loads vector data into a GeoDataFrame and reprojects if necessary."""
        if not self.vector_path or not os.path.exists(self.vector_path):
            raise FileNotFoundError(f"Vector file not found: {self.vector_path}")

        # Load vector
        gdf = gpd.read_file(self.vector_path)
        # Reproject to desired CRS (e.g., WGS84)
        if gdf.crs is not None and str(gdf.crs) != crs:
            gdf = gdf.to_crs(crs)

        self.vector_data = gdf
        return gdf

    def load_raster_data(self):
        """Loads raster data (e.g., DEM) to extract metadata for further analysis."""
        if not self.raster_path or not os.path.exists(self.raster_path):
            print("No valid raster path provided or file doesn't exist.")
            return None

        with rasterio.open(self.raster_path) as src:
            self.raster_meta = src.meta
        return self.raster_meta

    def fetch_weather_data(self, api_url, api_key):
        """
        Fetch external weather data (synchronously).
        In production, might want asynchronous approach or streaming.
        """
        params = {"api_key": api_key}
        response = requests.get(api_url, params=params)
        response.raise_for_status()
        return response.json()
