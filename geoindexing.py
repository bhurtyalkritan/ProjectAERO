# geoindexing.py
from rtree import index

class GeoIndexer:
    """Builds an R-tree index for optional no-fly zones."""
    def __init__(self, geodata):
        self.geodata = geodata
        self.spatial_index = None

    def build_spatial_index(self):
        """Builds the spatial index if data exists."""
        if self.geodata is None or self.geodata.empty:
            return
        prop = index.Property()
        prop.interleaved = True
        self.spatial_index = index.Index(properties=prop)
        for idx, row in self.geodata.iterrows():
            bounds = row.geometry.bounds
            self.spatial_index.insert(idx, bounds)

    def query(self, geometry):
        """Queries the index for intersecting geometries."""
        if not self.spatial_index:
            return []
        minx, miny, maxx, maxy = geometry.bounds
        candidate_ids = list(self.spatial_index.intersection((minx, miny, maxx, maxy)))
        return self.geodata.iloc[candidate_ids].copy()
