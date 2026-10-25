# Uploads the DSMW soil polygons to Supabase as the table "global_soils".
#
# Before running (PowerShell, same window):
#     $env:SUPABASE_DB_URL = "postgresql://..."      # your Session Pooler connection string
# After running:
#     python query_soil.py --setup                   # recreates the spatial index this upload deletes
# then re-check row-level security on global_soils in Supabase (see README).
import os
from pathlib import Path

import geopandas as gpd
from sqlalchemy import create_engine

# 1. The shapefile sits in the DSMW folder next to this script
shapefile_path = Path(__file__).resolve().parent / "DSMW" / "DSMW.shp"
if not shapefile_path.exists():
    raise SystemExit(f"Shapefile not found: {shapefile_path}\nDownload DSMW (see README) and unzip it into a folder called DSMW here.")

# 2. Connection string comes from the environment, never from this file
db_url = os.environ.get("SUPABASE_DB_URL")
if not db_url:
    raise SystemExit('Set SUPABASE_DB_URL first, e.g.  $env:SUPABASE_DB_URL = "postgresql://..."')
engine = create_engine(db_url)

print("Loading soil shapefile...")
gdf = gpd.read_file(shapefile_path)

# Ensure spatial reference system is standard WGS84 (latitude/longitude)
if gdf.crs is not None and gdf.crs.to_string() != "EPSG:4326":
    gdf = gdf.to_crs("EPSG:4326")

# 3. Upload. "replace" DROPS and recreates the table, so its index, permissions
#    and row-level security settings are lost and must be re-applied afterwards.
print("Uploading soil data to Supabase (this may take a minute or two)...")
gdf.to_postgis(
    name="global_soils",
    con=engine,
    if_exists="replace",
    index=False,
)

print("Success: soil polygons are in Supabase.")
print("Next: python query_soil.py --setup   and re-check row-level security on global_soils.")
