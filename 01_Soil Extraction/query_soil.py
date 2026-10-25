import pandas as pd
from sqlalchemy import create_engine

import os
DB_URL = os.environ["SUPABASE_DB_URL"]
engine = create_engine(DB_URL)

# One-time setup: adds the numeric join key and indexes.
# Safe to re-run (uses IF NOT EXISTS). Run with: python query_soil.py --setup
def setup():
    from sqlalchemy import text
    with engine.begin() as conn:
        # Force global_soils geometry to SRID 4326
        conn.execute(text('ALTER TABLE global_soils ALTER COLUMN geometry TYPE geometry(Geometry, 4326) USING ST_SetSRID(geometry, 4326);'))
        
        # Existing setup steps
        conn.execute(text('ALTER TABLE soil_attributes ADD COLUMN IF NOT EXISTS "SNUM" integer;'))
        conn.execute(text('''UPDATE soil_attributes
                             SET "SNUM" = substring("SNAM" from '([0-9]+)$')::int;'''))
        conn.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS soil_attributes_snum_idx ON soil_attributes ("SNUM");'))
        conn.execute(text('CREATE INDEX IF NOT EXISTS global_soils_geom_idx ON global_soils USING GIST (geometry);'))
    print("Setup done.")


def get_soil_properties(lat, lon):
    """Return a one-row DataFrame with soil polygon info + attributes, or None."""
    query = f"""
        SELECT g."SNUM", g."FAOSOIL", g."DOMSOI", g."CNTNAME", g."COUNTRY",
               a."SNAM", a."TEXTURE", a."HYDGRP",
               a."SOL_BD1", a."SOL_AWC1", a."SOL_K1",
               a."CLAY1", a."SILT1", a."SAND1"
        FROM global_soils g
        LEFT JOIN soil_attributes a ON a."SNUM" = g."SNUM"
        WHERE ST_Intersects(
            g.geometry,
            ST_SetSRID(ST_Point({float(lon)}, {float(lat)}), 4326)
        )
        LIMIT 1;
    """
    df = pd.read_sql(query, engine)
    return None if df.empty else df


if __name__ == "__main__":
    import sys

    if "--setup" in sys.argv:
        setup()
        sys.exit()

    tests = {
        "Barcelona": (41.3851, 2.1734),
        "Atacama": (-24.0, -69.0),
        "Mojave": (35.0, -116.0),
        "Sonoran": (32.5, -112.5),
    }
    for name, (lat, lon) in tests.items():
        print(f"\n=== {name} ({lat}, {lon}) ===")
        result = get_soil_properties(lat, lon)
        if result is None:
            print("No polygon found at this point.")
        else:
            for col in result.columns:
                print(f"  {col}: {result[col].values[0]}")