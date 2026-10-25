# ============================================================================
# COMPONENT 1: FETCH  (Rhino 7 GhPython or Rhino 8 Python 3 Script)
#
# Inputs   fetch  bool  Item   <- connect a Boolean Toggle or Button
#          url    str   Item   <- the "verified only" (or "everything") URL from the app's Settings tab
# Outputs  json_text  <- connect to components 2, 3 and 4
#          status
#
# Press the button: downloads the catalogue from Supabase and keeps a copy in memory and in
# a local cache file, so the other components keep working when you let go and after Rhino restarts.
# ============================================================================
import json, time
import scriptcontext as sc
from System.IO import File, Path
from System.Net import WebClient, ServicePointManager, SecurityProtocolType
from System.Text import Encoding

STICKY = "earth_catalogue_json"
CACHE = Path.Combine(Path.GetTempPath(), "earth_catalogue_cache.json")
CATALOGUE_URL = "https://widpcrwshasvkaudybjv.supabase.co/storage/v1/object/public/catalogue/earth_materials_catalogue_verified.json"


def describe(txt, prefix):
    d = json.loads(txt)
    return "%s: %d materials (exported %s)" % (prefix, len(d.get("materials", [])), str(d.get("exported_at", "?"))[:19])


json_text = sc.sticky.get(STICKY)
status = "Press the button to download the catalogue."
url = globals().get("url") or CATALOGUE_URL
try:
    if fetch:
        try:
            ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12   # needed on older .NET
        except Exception:
            pass
        wc = WebClient()
        wc.Encoding = Encoding.UTF8
        sep = "&" if "?" in url else "?"
        txt = wc.DownloadString(url + sep + "t=" + str(int(time.time())))     # t= defeats CDN caching
        d = json.loads(txt)
        if d.get("schema") != "earth_materials_catalogue":
            raise Exception("That URL did not return a catalogue export file.")
        sc.sticky[STICKY] = txt
        File.WriteAllText(CACHE, txt, Encoding.UTF8)
        json_text = txt
        status = describe(txt, "Downloaded")
    elif json_text:
        status = describe(json_text, "Using last download")
    elif File.Exists(CACHE):
        json_text = File.ReadAllText(CACHE, Encoding.UTF8)
        sc.sticky[STICKY] = json_text
        status = describe(json_text, "Loaded from local cache")
except Exception as e:
    status = "ERROR: " + str(e)
