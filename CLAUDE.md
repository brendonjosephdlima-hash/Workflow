# Project context: thesis workflow (soil extraction + earth-material catalogue)

The user has a **thesis review on 29 Oct 2026**: favour small, safe, verifiable changes over rewrites.
Windows 11 + PowerShell, Rhino 8 (Grasshopper Python 3 components), GitHub Desktop.
The user likes copy-pasteable text and step-by-step instructions.

Repo: https://github.com/brendonjosephdlima-hash/Workflow (public, default branch `master`)

---

## 1. What this is

One pipeline in Grasshopper:

```
01_Soil Extraction      pick a location -> regional soil (texture, clay/silt/sand, bulk density...) from Supabase/PostGIS (FAO DSMW)
        | clay1, silt1, sand1
        v
02_Material Catalogue   earth-material records extracted from papers with Gemini -> matched to that soil by construction method
```

## 2. Layout

```
Workflow/
  .gitignore  README.md  CLAUDE.md
  00_Grasshopper Env/
    Soil Import component.gh          <- the only Grasshopper definition (binary; scripts inside mirror the .py files)
  01_Soil Extraction/
    grasshopper/01_location_picker.py, 02_soil_extraction.py
    upload_soil.py  upload_attributes.py  query_soil.py  get_soil.sql  enable_rls.sql
    DSMW/                 (on disk, NOT in git)
    soil_data/soil_data.csv (on disk, NOT in git: ignored by *.csv; source still to be documented)
  02_Material Catalogue/earth-catalogue/
    app.py  prompt.txt  requirements.txt  .env.example  README.md
    static/index.html                 <- the whole UI, one file (vanilla JS + Tailwind CDN)
    grasshopper/01_fetch.py 02_decode.py 03_list_by_method.py 04_match.py 05_decode_best.py
                06_karamba_material.py 07_honeybee_material.py
    data/   (NOT in git: catalogue.json, pdfs/, backups/, exports/)
```

---

## 3. Catalogue app

**Run:** `cd "02_Material Catalogue/earth-catalogue"`, `pip install -r requirements.txt`, `.env` from `.env.example`,
`python app.py`, open http://127.0.0.1:8000. Python 3.10+.

**`prompt.txt` is read once when the server starts. Restart `python app.py` after editing it.**
It is the only copy of the extraction prompt (the browser never sees it).
`static/index.html` is served fresh, so a browser refresh (Ctrl+F5) is enough.

### app.py (Flask, localhost only)
| Endpoint | Purpose |
|---|---|
| `GET /` | serves `static/index.html` |
| `GET /api/status` | key configured?, model list, data dir, cloud URLs (never returns a key) |
| `GET/PUT /api/catalogue` | whole-catalogue load/save; atomic write; backup before any shrink, every 10 min, or when `force_backup: true`; refuses to overwrite an unreadable file |
| `GET /export.json[?verified_only=1]` | the Grasshopper export written at save time |
| `POST /api/pdfs`, `GET /api/pdfs/<sha256>` | content-addressed PDF store |
| `POST /api/extract` | calls Gemini with `prompt.txt`, model cascade (`GEMINI_MODELS`), PDF inline up to ~14 MB else text only (error if too big and no text) |
| `POST /api/test` | tries the models |
| `POST /api/publish` | uploads both export files to the Supabase Storage bucket |
| `GET /api/inbox` | scans `INBOX_DIR` (default `data/inbox`, recursive, *.pdf) into `data/inbox.json` keyed by sha256 (= PDF store id; unchanged path+size+mtime not re-hashed); returns present papers + `in_catalogue` |
| `POST /api/inbox/<id>/check` | imports the PDF into the store, runs `check_prompt.txt` via `run_models`, stores `check`, `verdict` (`recommended`/`partial`/`not_useful`/`not_relevant`), `domains`, `reason` (see `verdict()`) |
| `POST /api/inbox/<id>/import`, `/status` | copy into the PDF store; set status `new`/`checked`/`extracted`/`skipped` |

Guards: Host header must be localhost, every mutating request needs `X-Catalogue-Client: 1` and a same-origin
`Origin`, `Content-Security-Policy: connect-src 'self'`. Gemini key goes in the `x-goog-api-key` header.
Env vars: `GEMINI_API_KEY`, `GEMINI_MODELS`, `PORT`, `HOST`, `CATALOGUE_DATA`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`,
`SUPABASE_BUCKET` (default `catalogue`), `INBOX_DIR`. `check_prompt.txt` is read at start like `prompt.txt`. Default model IDs were chosen by the user and are unverified.

### index.html: key functions
- `normalizeMaterial(raw, paper, i)`: one model material -> record. `normTech` + `TECH_ALIASES` map techniques
  (unknown -> `other`). A 3D-printed mix keeps ONLY `3d_printed`; other tags go into the technique note.
  Labels are shortened: "(Author et al., 2020)" -> `cited_ref`, long trailing text -> `label_note`.
  `deriveTags` adds `fibre_reinforced`, `stabilised_*`, `unstabilised`.
- On load, a migration tidies existing records the same way (names, `cited_ref`, 3D-printed tags) and notifies
  "Tidied N record(s)... Remember to publish". The cloud export only changes after **Publish**.
- `applyDerived`: exact derived values, provenance type `derived`: vhc, diffusivity, and from `raw_data` dry density
  (mass / prism or cylinder volume) and E (slope of two elastic stress-strain points). Strain > 0.03 is treated as a
  % unit slip: E not calculated, flag `raw_strain_looks_like_percent`. `raw_*` flags are reset on every run.
- `DOMAINS` + `readiness(it)`: mechanical (trigger fc/E/ft/ff, needs fc + E + rho, for Karamba) and thermal (trigger
  lambda/cp/alpha, needs lambda + rho + cp, for Honeybee). Levels `ready` (reported/manual/derived), `estimated`,
  `incomplete`. Shown as MECH/THERM badges (`readinessHtml`), in stats, and as `filter-data` options `mechanical[:ready]`.
- `mergeOrInsert` + `dedupeKey` (`doi|label|cited_ref|test_conditions`, lowercased): never overwrites values.
- `completeProperties` / `getCompleted` (cache `completeCache`, reset in `saveState`): export-time completion (section 5).
- `buildExportRecord`, `buildExportPayload`, `persistCatalogue`, `publishToCloud`, `renderTable` (REP/CALC/EST badges,
  "cited: <ref>" under the id), `openAuditModal`, `openSpecModal`.
- `catalogueLoaded` blocks saving until the server copy was read.
- **Inbox tab** (`loadInbox` on start, `renderInbox`, `checkInbox`, `extractInbox`, `extractRecommended`): sequential
  check / import + `/api/extract` + `recordsFromResult` + `mergeOrInsert`, then `saveState` and `showReview(pdfIds)`.
  `recordsFromResult` is shared with re-extraction.
- **Re-extraction** (`reextractPapers(pdfIds?)`, button "Re-extract papers" + "Re-extract this paper" in the Sheet):
  re-runs `/api/extract` on stored PDFs (pdf_id only, no text) and reconciles per paper. `pairScore` pairs new with
  old records (equal values +3 / differing -1, composition pct matches, label/test-condition word overlap, technique,
  cited_ref; threshold 2, greedy). `carryOver`: new record takes the old id; equal values keep verification; a value
  that differs from a verified/manual one keeps the old value and logs the new one in `cross_references`; verified
  values the new run missed are restored; unverified ones are replaced. Unpaired new -> added (`EM-<base>-R<n>`),
  unpaired old -> kept + flag `not_found_on_reextract`. Nothing changes until Apply in the summary modal (reuses the
  Sheet modal); Apply forces a server backup (`force_backup` in the PUT body) and skips papers edited during the run.
  New keys (e.g. raw_data) are unverified, so such records leave the verified-only export until audited.
- **Review** (`showReview(paperKeys|null)`, toolbar "Review (N)", opens automatically after Apply): per paper, records
  with unverified keys (click -> audit modal, closing it returns to the review via `reviewReturn`), re-extraction
  conflicts (`cross_references` with `kind:'reextract'` + `new_data` = `keyFields()` snapshot; "Use new" applies it
  unverified, "Keep verified" drops it; old text-only conflicts can only be kept until the paper is re-extracted
  again, which replaces them), and `not_found_on_reextract` records (Keep / Delete). "Verify all values of this
  paper" asks first and logs `verified_by: '<name> (bulk, after re-extraction)'`.

### Record shape (main fields)
`id`, `material_label`, `label_original` (pre-migration name), `label_note`, `cited_ref`, `technique_tags[]`, `technique_note`, `tags[]`,
`paper{title,doi,year,soil_origin,pdf_id}`, `soil_fractions{clay_pct,silt_pct,sand_pct,gravel_pct,note}`,
`raw_data{specimen_shape,length_mm,width_mm,height_mm,diameter_mm,dry_mass_g,stress_strain[2]}` (auditable key
`raw_data`), `soil_fractions_source` (`reported` | `computed_from_composition`), `soil_texture_class`, `composition[]`
(categories incl. `soil` for natural soil of unknown grading), `properties{}` (14 keys),
`provenance{key:{type,page,quote,from_figure,verified,pdf_id}}`, `curing`, `test_conditions`, `data_origin`, `flags[]`.

Property keys: `dry_density_kg_m3, porosity_pct, thermal_conductivity_W_mK, specific_heat_J_kgK,
thermal_diffusivity_mm2_s, volumetric_heat_capacity_MJ_m3K, decrement_factor, time_lag_h, compressive_strength_MPa,
tensile_strength_MPa, flexural_strength_MPa, elastic_modulus_MPa, poisson_ratio, shrinkage_pct, water_absorption_pct`.
`isFullyVerified` = every audit key verified. `isMatchReady` = clay, silt and sand all non-null.

---

## 4. Export JSON (what Grasshopper reads)

`{schema:"earth_materials_catalogue", version:1, exported_at, count, verified_only, materials:[...]}`; each material:
`id, name, techniques[], tags[], domains[], readiness{mechanical|thermal:{level,missing[],estimated[]}}, soil{clay_pct,silt_pct,sand_pct,gravel_pct,texture_class,source,match_ready},
composition[], summary, properties{}, property_basis{}, property_notes{}, verified{}, verified_ratio,
fully_verified, curing, test_conditions, data_origin, source{cited_ref,doi,title,year,soil_origin,pages}, flags[]`.

Two files in the public bucket `catalogue`: `earth_materials_catalogue.json` (everything) and
`earth_materials_catalogue_verified.json` (only `fully_verified`). The fetch URL decides what Grasshopper sees.

Snapshot 2026-10-27: 44 records, all verified, 19 match_ready (rammed earth: 3 of 12 have soil data).
Methods: other 16, rammed_earth 12, 3d_printed 9, adobe 5, cob 2.
Domains: 28 mechanical (3 ready, 9 estimated, 16 incomplete), 16 thermal (all incomplete: none report density or
cp), 0 both. Papers report either thermal or mechanical data, almost never both.

---

## 5. Property completion (export only, nothing written back to records)

Tags: **extracted** (reported/manual), **computed** (exact identity), **estimated** (statistical, with a note).
- Exact: vhc = rho*cp/1e6; alpha = lam/vhc; solved in any direction when one is missing.
- Estimated, calibrated only on OTHER records' extracted values: ff, ft, E = fc x median ratio (>=3 same-method or
  >=5 any); cp = median; lam = log-log power-law on density (>=5 same-method or >=8 any, R2 >= 0.5, density inside
  the fitted range); porosity = 1 - rho/2650. A value built on an estimate is `estimated`. Implausible values skipped.
- Never estimated: decrement factor, time lag, shrinkage, water absorption.

---

## 6. Grasshopper components

Python files are the **source of truth**; they are pasted inside the `.gh`. Edit the `.py`, then tell the user
to repaste. Inputs/outputs are created by hand, named as in each script's header comment.

| File | Role |
|---|---|
| `01_fetch.py` | Button -> downloads the JSON (cache-buster `?t=`), keeps it in `sc.sticky` + a temp file. `CATALOGUE_URL` constant, overridable by `url`. |
| `02_decode.py` | catalogue -> aligned lists: ids, names, techniques, `methods_present`, soil %, texture, match_ready, rho, lam, cp, fc, ff, verified, doi, year. |
| `03_list_by_method.py` | `method` -> materials with that tag; optional `only_verified`. |
| `04_match.py` | site clay/silt/sand + `method` -> ranked by match % = 100 - 0.5*sum(|delta|) after rescaling to 100; `correction`; optional `only_verified, min_match, min_fc, max_lambda, top_n`; `best` JSON. Only `match_ready` records are scored; the report names same-method materials left out for missing soil data. Optional `domain` (`mechanical`/`thermal`) keeps only `ready` records for that domain (`allow_estimates` adds `estimated`). |
| `05_decode_best.py` | `best` JSON -> scalar outputs + `missing`. |
| `06_karamba_material.py` | `best` -> E, G, gamma, alphaT (always null), ft, fc in kN/cm2 / kN/m3; optional `nu` (assumed Poisson, default 0.2, used only if the paper has none), `allow_estimates`; `ready`, `assumptions`, `report`. |
| `07_honeybee_material.py` | `best` + `thickness` (m) -> name, thickness_m, conductivity, density, spec_heat for HB Opaque Material; optional `cp` (assumed), `allow_estimates`; `material` = EnergyMaterial if `honeybee_energy` imports, else null. |

Method Value List: `3d_printed`, `cob`, `adobe`, `rammed_earth`, `compressed_earth_block`, `cast_earth`,
`wattle_and_daub`, `earthbag`, `other`. Names are normalised (case, spaces, hyphens, slashes -> underscore).

`04_match` inputs in the user's definition (2026-10-27): json_text, method, site_clay, site_silt, site_sand,
only_verified, min_fc, max_lambda, top_n (no `min_match` input; optional). The old `min_lambda` name was fixed.

---

## 7. Supabase and secrets

- Bucket `catalogue` (public); tables `global_soils` (PostGIS) and `soil_attributes`; function `get_soil(lat, lon)`
  via `/rest/v1/rpc/get_soil`.
- The **publishable** key is in `02_soil_extraction.py` (public by design, safe only with RLS on).
  The service_role key, Gemini key and `SUPABASE_DB_URL` go in `.env` / environment variables only. Never print them.
- Uploads use `if_exists="replace"` (drops the table). After every upload: `python query_soil.py --setup`, then run
  `enable_rls.sql` (read-only policies + revoked writes for anon/authenticated). If `get_soil` then returns nothing,
  recreate it with `security definer set search_path = public, extensions`.
- RLS enabled on both tables 2026-10-27 (enable_rls.sql run, `rowsecurity = true` confirmed).
  Still to confirm: the Grasshopper soil component returns data with RLS on.

---

## 8. Git rules

`.gitignore` keeps out `.env*` (except `.env.example`), `data/`, `DSMW/`, GIS/spreadsheet types, `*.3dm*`, `*.rhl`,
Python/IDE/OS junk. `data/` holds copyrighted PDFs and must never be committed. Already-tracked files ignore later
rules: check with `git ls-files | Select-String "DSMW","\.3dm","\.env","/data/","\.pdf$","\.csv$"`
(only `.env.example` should match). Commit small; the user pushes from GitHub Desktop.

---

## 9. Open issues

### 9.1 Odd material names: mostly done
Prompt rule (<=40 chars, no authors/years) + `cited_ref` field + load-time migration are in. Remaining:
- the published export still has old names until the user opens the app and clicks **Publish**;
- the migration keeps abbreviations like "SRE", "Cem", "FA/BA" (it only strips citations);
- no rename action in the UI (`dedupeKey` includes the label, so renaming affects duplicate detection).

### 9.2 Rammed earth "missing" in Grasshopper: explained, report improved
`04_match` scores only records with clay/silt/sand. 9 of 12 rammed-earth records are cited review records without
soil data. `04`'s report now lists them by name. Still to decide: should cited records without soil data be matched
some other way (e.g. by texture class), or stay excluded?

### 9.3 3D-printed papers tagged adobe: mostly done
Prompt rule 2 + normaliser force `3d_printed` only. Remaining: keyword scan (3D print, additive manufacturing,
extrusion, printable, robocasting) that flags records missing `3d_printed`; an "edit methods" action. Verify by
re-extracting one known 3D-printing paper (needs Gemini).

### 9.4 Mechanical / thermal split (built 2026-10-27, not yet run against real Gemini or in Rhino)
- Prompt asks for `poisson_ratio` and `raw_data`; only NEW extractions get them. Existing records are unchanged.
- No thermal record reports density or cp, so no material can feed Honeybee yet: thermal papers that report
  density (and cp or diffusivity) are needed. 07 accepts an assumed `cp` but still needs density.
- Karamba fc sign convention depends on the Karamba version (06 outputs it positive).
- Tests used for this: Node vm harness around the page script + exec of the GH scripts on a generated export
  (kept outside the repo).

### 9.5 Other
- RLS is on; confirm the soil component still returns data.
- Document where `soil_data.csv` came from (it is SWAT-format: SNAM, HYDGRP, SOL_BD1, CLAY1...).
- Add a LICENSE if the repo should be reusable.

---

## 10. Known limitations

- No `responseSchema` (structured output); PDFs over ~14 MB send text only.
- CDN scripts (Tailwind, pdf.js, SheetJS) load without integrity hashes.
- No Poisson's ratio. Decrement factor / time lag would need wall thickness.
- Duplicate detection is exact on `doi|label|cited_ref|test_conditions`.
- Matching compares soil texture only (not mineralogy or additives).

---

## 11. Testing

**When testing app.py, always set `GEMINI_API_KEY=x` (or mock `gemini_call`)**: `load_dotenv` reads the real `.env`, so an
unmocked check/extract in a test calls Gemini with the user's key (happened once on 2026-10-27, a 16-byte fake PDF).

No `tests/` folder yet. Quick checks that work:
- `04_match.py` (and the other GH scripts) can be run with plain Python by `exec`-ing the file with injected inputs
  (`json_text` from `data/exports/earth_materials_catalogue.json`, `method`, `site_clay/silt/sand`).
- `index.html`: extract the inline `<script>` and run `node --check` on it after every edit.
Nothing has been run against real Gemini, real Supabase or inside Rhino by the assistant.

---

## 12. Working agreements

- Keep changes small; tell the user exactly which files changed and what to restart, refresh, repaste or publish.
- Never read, print or write secrets; never commit `.env`, `data/`, `DSMW/`.
- Do not invent property values; anything not from a paper is tagged and carries a note.
- After any change to `index.html`, run `node --check` and verify behaviour before saying it works.
