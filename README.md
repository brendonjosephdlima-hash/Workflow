# Thesis workflow: from site soil to earth-material match

Two parts that feed one Grasshopper workflow.

```
01_Soil Extraction          pick a location -> regional soil data (texture, bulk density, ...)
        |  clay / silt / sand  (clay1, silt1, sand1)
        v
02_Material Catalogue       earth-material records extracted from papers -> matched to that soil
```

## 01_Soil Extraction
Looks up the soil at a chosen location from a Supabase (PostGIS) database built from the DSMW soil map.

| File | What it does |
|---|---|
| `get_soil.sql` | PostgreSQL function for spatial soil lookups (run in Supabase SQL Editor) |
| `grasshopper/01_location_picker.py` | lets you pick a location in Rhino instead of typing latitude and longitude |
| `grasshopper/02_soil_extraction.py` | takes lat/lon, calls the Supabase `get_soil` function, outputs texture, bulk density, clay/silt/sand, ... |
| `upload_soil.py` | uploads the DSMW polygons (`DSMW/DSMW.shp`) to the table `global_soils` |
| `upload_attributes.py` | uploads `soil_data/soil_data.csv` to the table `soil_attributes` |
| `query_soil.py` | test lookups at four places; `--setup` adds the `SNUM` join column and the spatial index |
| `enable_rls.sql` | row-level security for both tables (run once in the Supabase SQL Editor) |
| `Soil Import component.gh` | Grasshopper definition |

**Rebuilding the database** (the upload scripts read the connection string from the environment):

    $env:SUPABASE_DB_URL = "postgresql://..."     # PowerShell, same window
    python upload_soil.py
    python upload_attributes.py
    python query_soil.py --setup                  # the uploads delete the join column and index
    # then run enable_rls.sql in Supabase and test the soil component in Grasshopper

Both uploads use `if_exists="replace"`, which drops and recreates the table. That is why `--setup` and the
row-level security step have to be repeated after every re-upload.

The `get_soil` SQL function (defined in `get_soil.sql`) needs to be created in your Supabase project (run it once in the Supabase SQL Editor).

**Source data:** FAO/UNESCO Digital Soil Map of the World (DSMW), Version 3.6 (2003). Downloadable via the [FAO Soils Portal](https://www.fao.org/soils-portal/data-hub/soil-maps-and-databases/faounesco-soil-map-of-the-world/en/) (the `DSMW/` folder is omitted from this repo due to file size).

## 02_Material Catalogue
`earth-catalogue/` is a local app (Python + HTML) that extracts earth-material data from research papers with
Gemini, keeps the records and source PDFs on disk, and publishes a JSON export to Supabase Storage. The
Grasshopper scripts in `earth-catalogue/grasshopper/` download that JSON and match the site soil to materials
by construction method. See `02_Material Catalogue/earth-catalogue/README.md` for setup.

## Secrets (read before you run anything)
Keys are never stored in this repo.

- Copy `.env.example` to `.env` (inside `earth-catalogue/`) and fill in your own keys.
- `.env` and the `data/` folder (records and PDFs) are git-ignored on purpose.
- The Supabase **publishable** key in the Grasshopper scripts is designed to be public, but only if the database
  does not let it change anything: run `enable_rls.sql` and confirm row-level security is on for both soil tables.
- Any secret or service-role key must stay in `.env` or an environment variable, never in a script or a `.gh` file.

## Getting started
1. Clone the repo.
2. `cd "02_Material Catalogue/earth-catalogue"`, then `pip install -r requirements.txt`.
3. Create `.env` from `.env.example`, then run `python app.py`.
4. Open the Grasshopper definitions and point the fetch component at your Supabase file URL.

## Working on it
- The `.py` files are the source of truth for all Grasshopper scripts. When you change a script inside a
  `.gh` file, copy it back to its `.py` file before committing (`.gh` files are binary and cannot be compared).
- Commit small, with messages that say what changed.
