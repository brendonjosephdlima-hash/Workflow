import re
import Rhino
import scriptcontext as sc
import Eto.Forms as ef
import Eto.Drawing as ed

KEY = "soil_map_pick"

HTML = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>map</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.css"/>
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.js"></script>
<style>
  html, body { margin:0; height:100%; font-family:Segoe UI, Arial, sans-serif; }
  #bar { height:48px; display:flex; align-items:center; gap:12px; padding:0 12px; background:#f0f0f0; }
  #map { height:calc(100% - 48px); }
  button { padding:6px 14px; font-size:14px; }
</style>
</head>
<body>
<div id="bar">
  <span id="info">Click on the map to place a marker</span>
  <button onclick="confirmPick()">Use this location</button>
</div>
<div id="map"></div>
<script>
  var map = L.map('map').setView([START_LAT, START_LON], START_ZOOM);
  L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
              {maxZoom: 18, attribution: 'Esri'}).addTo(map);
  var marker = null, pos = null;
  map.on('click', function(e) {
    pos = e.latlng;
    if (marker) { marker.setLatLng(pos); } else { marker = L.marker(pos).addTo(map); }
    document.getElementById('info').innerText =
      'lat ' + pos.lat.toFixed(5) + '   lon ' + pos.lng.toFixed(5);
  });
  function confirmPick() {
    if (!pos) { document.getElementById('info').innerText = 'Click the map first'; return; }
    document.title = 'PICK:' + pos.lat.toFixed(5) + ',' + pos.lng.toFixed(5);
  }
</script>
</body>
</html>
"""

def pick_location(lat0, lon0):
    result = {}
    if lat0 is not None and lon0 is not None:
        html = (HTML.replace("START_LAT", str(float(lat0)))
                    .replace("START_LON", str(float(lon0)))
                    .replace("START_ZOOM", "6"))
    else:
        html = (HTML.replace("START_LAT", "20")
                    .replace("START_LON", "0")
                    .replace("START_ZOOM", "2"))

    dlg = ef.Dialog()
    dlg.Title = "Pick a location"
    dlg.ClientSize = ed.Size(950, 700)
    dlg.Resizable = True

    web = ef.WebView()

    def on_title(sender, e):
        title = str(e.Title)
        if title.startswith("PICK:"):
            nums = re.findall(r"-?\d+\.?\d*", title)
            if len(nums) >= 2:
                result["lat"] = float(nums[0])
                result["lon"] = float(nums[1])
            dlg.Close()

    web.DocumentTitleChanged += on_title
    web.LoadHtml(html)
    dlg.Content = web
    dlg.ShowModal(Rhino.UI.RhinoEtoApp.MainWindow)

    if "lat" in result:
        return (result["lat"], result["lon"])
    return None

# Open the map when the button is pressed
if pick:
    picked = pick_location(lat0, lon0)
    if picked:
        sc.sticky[KEY] = picked

# Always output the last picked location
saved = sc.sticky.get(KEY)
if saved:
    lat, lon = saved
else:
    lat, lon = None, None