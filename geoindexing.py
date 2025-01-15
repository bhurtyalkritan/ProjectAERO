import geopandas as gpd
from shapely.geometry import shape, box
from rtree import index


class GeoIndexer:
    def __init__(self, geodata: gpd.GeoDataFrame):
        """
        :param geodata: A GeoDataFrame with geometric features (e.g., restricted zones)
        """
        self.geodata = geodata
        self.spatial_index = None

    def build_spatial_index(self):
        """Build an R-tree index for quick bounding-box queries."""
        if self.geodata is None or self.geodata.empty:
            raise ValueError("No GeoDataFrame loaded for indexing.")

        # R-tree index creation
        prop = index.Property()
        prop.interleaved = True
        self.spatial_index = index.Index(properties=prop)

        for idx, row in self.geodata.iterrows():
            geom_bounds = row.geometry.bounds  # (minx, miny, maxx, maxy)
            self.spatial_index.insert(idx, geom_bounds)

    def query(self, query_geom):
        """
        Query the R-tree index for features whose bounding boxes intersect with `query_geom`.
        Returns a subset GeoDataFrame of matching features.
        """
        if not self.spatial_index:
            raise RuntimeError("Spatial index not built. Call build_spatial_index() first.")

        minx, miny, maxx, maxy = query_geom.bounds
        candidate_ids = list(self.spatial_index.intersection((minx, miny, maxx, maxy)))
        return self.geodata.iloc[candidate_ids].copy()
