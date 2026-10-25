import json
import urllib.request

SUPABASE_URL = "https://widpcrwshasvkaudybjv.supabase.co"
SUPABASE_KEY = "sb_publishable_nnucQOoiBqRPhgjhAAuEbQ_nQJMFkX-"

def fetch_soil(lat, lon):
    url = SUPABASE_URL + "/rest/v1/rpc/get_soil"
    headers = {
        "apikey": SUPABASE_KEY,
        "Content-Type": "application/json",
        "User-Agent": "soil-plugin",
    }
    if SUPABASE_KEY.startswith("eyJ"):
        headers["Authorization"] = "Bearer " + SUPABASE_KEY
    body = json.dumps({"lat": float(lat), "lon": float(lon)}).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"Soil lookup error: {e}")
        return None

# Component Execution Logic
if run and lat is not None and lon is not None:
    data = fetch_soil(lat, lon)

    if data:
        texture = str(data.get("TEXTURE") or "N/A")
        bd1  = float(data.get("SOL_BD1") or 0.0)
        awc1 = float(data.get("SOL_AWC1") or 0.0)
        k1   = float(data.get("SOL_K1") or 0.0)
        hydgrp = str(data.get("HYDGRP") or "N/A")
        country = str(data.get("COUNTRY") or "N/A")
        clay1 = float(data.get("CLAY1") or 0.0)
        silt1 = float(data.get("SILT1") or 0.0)
        sand1 = float(data.get("SAND1") or 0.0)

        non_soil = texture in ("UWB", "N/A") or k1 >= 99
        soil_valid = not non_soil

        soil = f"Location: {country}\nTexture: {texture}\nHydgrp: {hydgrp}\nBulk Density: {bd1}"
    else:
        soil = "No soil polygon found at coordinates."
        texture, bd1, awc1, k1, hydgrp = "N/A", 0.0, 0.0, 0.0, "N/A"
        clay1, silt1, sand1 = 0.0, 0.0, 0.0
        soil_valid = False
else:
    soil = "Set 'run' to True and provide lat/lon."
    texture, bd1, awc1, k1, hydgrp = "N/A", 0.0, 0.0, 0.0, "N/A"
    clay1, silt1, sand1 = 0.0, 0.0, 0.0
    soil_valid = False