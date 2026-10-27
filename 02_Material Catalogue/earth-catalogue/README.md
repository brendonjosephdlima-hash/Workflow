# Earth Materials Catalogue (Python + HTML)

## Run it
Requires Python 3.10+.

    pip install -r requirements.txt
    cp .env.example .env        # then put your Gemini key in .env
    python app.py

Open http://127.0.0.1:8000 (not the HTML file directly).

## Where things live
    app.py              server: holds the key, calls Gemini, stores data
    prompt.txt          the extraction prompt (edit here, restart the server)
    static/index.html   the UI
    data/catalogue.json all records (written atomically)
    data/pdfs/          source PDFs, named by hash; the audit view reads these
    data/backups/       rolling copies of catalogue.json (always taken before a deletion)
    data/exports/       Grasshopper JSON, rewritten on every save

## After changing prompt.txt: re-extract
Restart `python app.py`, then click **Re-extract papers** in the catalogue (or "Re-extract this paper" in a
material's Sheet). Every stored PDF is read again with the new prompt. You get a summary before anything changes:
values that come out the same stay verified, a value that differs from one you verified is NOT replaced (the new
one is logged as a conflict), and new values arrive unverified. Apply makes a backup first. Then audit and Publish.

To move the catalogue to another machine, copy the whole `data/` folder.
The in-app "Backup" button does NOT include the PDFs.

## Cloud copy (Supabase) and Grasshopper

### One-time Supabase setup
1. supabase.com -> create a project.
2. Storage -> New bucket -> name `catalogue` -> turn **Public bucket** on.
   (Public means anyone with the URL can read the catalogue JSON. Writing always needs your secret key.)
3. Project Settings -> API: copy the **Project URL** and the **secret / service_role key**.
4. Put them in `.env` (the secret key stays here, never in Grasshopper):

       SUPABASE_URL=https://YOUR-PROJECT-REF.supabase.co
       SUPABASE_SERVICE_KEY=...
       SUPABASE_BUCKET=catalogue

5. Restart `python app.py`. Click **Publish to cloud** in the app. The two Grasshopper URLs appear in Settings.

### Grasshopper components (folder `grasshopper/`)
Make four Python components (Rhino 8: Python 3 Script; Rhino 7: GhPython) and paste one script into each.
Create the inputs/outputs named in the header comment of each script, and set type hints
(str / bool / float / int, Item access).

    01_fetch.py            Button -> downloads the JSON from Supabase, caches it
    02_decode.py           splits it into aligned lists (names, methods, soil, thermal, strength...)
    03_list_by_method.py   pick a construction method -> the materials available for it
    04_match.py            site clay/silt/sand + method -> ranked closest catalogue materials
                           optional domain = "mechanical" | "thermal": only materials with the minimum for that tool
    05_decode_best.py      best match -> every property as a single value
    06_karamba_material.py best match -> E, G, gamma, alphaT, ft, fc in Karamba units (kN/cm2, kN/m3)
    07_honeybee_material.py best match + wall thickness -> conductivity, density, specific heat for HB Opaque Material

Wiring: Button -> 01.fetch; Panel with the URL -> 01.url; 01.json_text -> 02, 03 and 04.json_text;
04.best -> 05, 06 and 07.best.

Mechanical vs thermal: every material is labelled mechanical and/or thermal, with a readiness level.
- mechanical (Karamba) needs fc, E and dry density; thermal (Honeybee) needs conductivity, dry density and specific heat
- ready = all of them come from the paper (reported, or calculated from its own data, e.g. density from specimen
  mass and size, E from the stress-strain curve, cp from conductivity / (density x diffusivity))
- estimated = complete only thanks to a catalogue estimate; incomplete = something missing
06 and 07 list every assumption they make (Poisson's ratio for G, a cp you supply) in their report.
For the method picker, add a **Value List** and give it these items (name = value):
3D printed = 3d_printed, Cob = cob, Adobe = adobe, Rammed earth = rammed_earth,
Compressed earth block = compressed_earth_block, Cast earth = cast_earth,
Wattle and daub = wattle_and_daub, Earthbag = earthbag, Other = other. Connect it to `method` on 03 and 04.

### Direct file / local URL (no Supabase)
The server must be running for the URL. The file works without it.

    # GhPython (Rhino 7 or 8)
    import json
    from System.Net import WebClient
    url = "http://127.0.0.1:8000/export.json?verified_only=1"   # drop the query for everything
    data = json.loads(WebClient().DownloadString(url))
    materials = data["materials"]       # each has soil, properties, verified, source...

    # or, with no server: read data/exports/earth_materials_catalogue_verified.json

The export files are written when the app saves, so open the app and save something once
before the first fetch.

## Security notes
- The key is only in `.env` / the environment. It is sent to Google in a header, never in a URL,
  and no endpoint returns it.
- The server binds to 127.0.0.1 and rejects other Host headers and cross-site requests, so
  other web pages in your browser cannot use it. Do not set HOST=0.0.0.0 unless you add a login.
- Set a spending cap and restrict the key to the Generative Language API in Google AI Studio / Cloud Console.
- A key that was ever pasted into the old HTML file lives in that browser's localStorage and in
  anywhere you shared the file. Create a new key and delete the old one.
