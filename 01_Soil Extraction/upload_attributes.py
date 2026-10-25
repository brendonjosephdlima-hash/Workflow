# Uploads soil_data.csv to Supabase as the table "soil_attributes".
#
# Before running (PowerShell, same window):
#     $env:SUPABASE_DB_URL = "postgresql://..."      # your Session Pooler connection string
# After running:
#     python query_soil.py --setup                   # recreates the SNUM join column this upload deletes
# then re-check row-level security on soil_attributes in Supabase (see README).
import os
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine

# 1. Connection string comes from the environment, never from this file
db_url = os.environ.get("SUPABASE_DB_URL")
if not db_url:
    raise SystemExit('Set SUPABASE_DB_URL first, e.g.  $env:SUPABASE_DB_URL = "postgresql://..."')
engine = create_engine(db_url)

# 2. soil_data.csv: look in the soil_data folder first, then next to this script
here = Path(__file__).resolve().parent
candidates = [here / "soil_data" / "soil_data.csv", here / "soil_data.csv"]
csv_path = next((p for p in candidates if p.exists()), None)
if csv_path is None:
    raise SystemExit("soil_data.csv not found. Looked in:\n  " + "\n  ".join(str(p) for p in candidates))

print(f"Loading soil attribute CSV: {csv_path}")
df = pd.read_csv(csv_path)

# 3. Upload. "replace" DROPS and recreates the table, so the SNUM column, its index,
#    permissions and row-level security settings are lost and must be re-applied afterwards.
print("Uploading attributes to Supabase...")
df.to_sql(
    name="soil_attributes",
    con=engine,
    if_exists="replace",
    index=False,
)

print("Success: soil attributes are in Supabase.")
print("Next: python query_soil.py --setup   and re-check row-level security on soil_attributes.")
