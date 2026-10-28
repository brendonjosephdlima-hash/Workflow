# Builds the world soil map used by the catalogue's "Where can I build this?" view.
#
#     python build_soil_map.py
#
# Reads DSMW/DSMW.shp + soil_data/soil_data.csv (the same data as the Supabase tables), joins topsoil
# clay/silt/sand onto each soil unit, merges polygons per soil unit and country, simplifies them and writes
#     ../02_Material Catalogue/earth-catalogue/data/soil_map.geojson
# (inside data/, so it is not committed: it is derived from DSMW). Run it again only if the soil data changes.
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "02_Material Catalogue" / "earth-catalogue" / "data" / "soil_map.geojson"
TOLERANCE = 0.08   # degrees (~9 km): plenty for a world view of a 1:5,000,000 map

g = gpd.read_file(HERE / "DSMW" / "DSMW.shp")
if g.crs is None:
    g = g.set_crs(4326)          # DSMW is in WGS84 lon/lat (get_soil uses SRID 4326 too)

a = pd.read_csv(HERE / "soil_data" / "soil_data.csv", usecols=["SNAM", "TEXTURE", "CLAY1", "SILT1", "SAND1"])
a["SNUM"] = a["SNAM"].str.extract(r"(\d+)$")[0].astype(int)   # same rule as query_soil.py --setup
a = a.drop_duplicates("SNUM")

g = g.merge(a, on="SNUM", how="left")

# country outlines from the same polygons (before dropping water / rock), for the map background
c = g[["COUNTRY", "geometry"]].dissolve(by="COUNTRY", as_index=False)
c["geometry"] = c.geometry.simplify(TOLERANCE, preserve_topology=True)
c = c[~c.geometry.is_empty]
g = g[g[["CLAY1", "SILT1", "SAND1"]].notna().all(axis=1)]
g = g[(g["CLAY1"] + g["SILT1"] + g["SAND1"]) > 0]          # water, glaciers, rock outcrops have no texture

g = g.dissolve(by=["SNUM", "COUNTRY"], as_index=False, aggfunc={
    "FAOSOIL": "first", "TEXTURE": "first", "CLAY1": "first", "SILT1": "first", "SAND1": "first", "SQKM": "sum"})
g["geometry"] = g.geometry.simplify(TOLERANCE, preserve_topology=True)
g = g[~g.geometry.is_empty]

def rnd(x):
    return [rnd(v) for v in x] if isinstance(x[0], (list, tuple)) else [round(x[0], 2), round(x[1], 2)]


def geojson(geom):
    geo = json.loads(gpd.GeoSeries([geom]).to_json())["features"][0]["geometry"]
    geo["coordinates"] = rnd(geo["coordinates"])
    return geo


features = []
for r in g.itertuples():
    geo = geojson(r.geometry)
    features.append({"type": "Feature", "geometry": geo, "properties": {
        "snum": int(r.SNUM), "country": str(r.COUNTRY).title(), "fao": r.FAOSOIL, "texture": str(r.TEXTURE).replace("_", " ").lower(),
        "clay": float(r.CLAY1), "silt": float(r.SILT1), "sand": float(r.SAND1), "sqkm": float(r.SQKM)}})

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps({"type": "FeatureCollection", "source": "FAO DSMW topsoil (CLAY1/SILT1/SAND1)",
                           "features": features}, separators=(",", ":")), encoding="utf-8")
print(f"{len(features)} soil areas -> {OUT} ({OUT.stat().st_size / 2**20:.1f} MB)")

OUT_C = OUT.with_name("countries.geojson")
OUT_C.write_text(json.dumps({"type": "FeatureCollection", "source": "FAO DSMW, dissolved per country", "features": [
    {"type": "Feature", "geometry": geojson(r.geometry), "properties": {"country": str(r.COUNTRY).title()}}
    for r in c.itertuples()]}, separators=(",", ":")), encoding="utf-8")
print(f"{len(c)} countries -> {OUT_C} ({OUT_C.stat().st_size / 2**20:.1f} MB)")
