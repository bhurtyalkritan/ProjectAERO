import geopandas as gpd
import os

class DataIngestionETL:
    """Loads optional no-fly zones from a local vector file."""
    def __init__(self, vector_path=None):
        self.vector_path = vector_path
        self.vector_data = None

    def load_vector_data(self, crs="EPSG:4326"):
        """Loads and reprojects the no-fly zones if available."""
        if not self.vector_path or not os.path.exists(self.vector_path):
            return None
        gdf = gpd.read_file(self.vector_path)
        if gdf.crs and str(gdf.crs) != crs:
            gdf = gdf.to_crs(crs)
        self.vector_data = gdf
        return gdf
