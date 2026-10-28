# ============================================================================
# COMPONENT 8: WHERE CAN I BUILD THIS?  (reverse of component 4: material -> world map of matching soils)
#
# Inputs   json_text    str    Item   <- from component 1
#          material_id  str    Item   <- an id from component 3 (List Item on its 'ids'), e.g. "EM-..."
#          soil_map     str    Item   <- full path to data/soil_map.geojson (File Path component or Panel).
#                                        Made once with:  python "01_Soil Extraction/build_soil_map.py"
#          min_match    float  Item (optional)  areas at or above this count as buildable, default 80
#          scale        float  Item (optional)  model units per degree, default 1 (x = longitude, y = latitude)
#          only_matching bool  Item (optional)  True = draw only areas >= min_match (faster, cleaner)
# Outputs  meshes, colors     one coloured mesh per soil area (Custom Preview: meshes -> Geometry, colors -> Material)
#          outlines           the area boundaries as closed polylines, same order
#          match, country, texture   per area, same order
#          countries, country_area_km2, country_best   countries ranked by buildable area (>= min_match)
#          recipe, report
#
# Match = same score as component 4: both soils rescaled to clay+silt+sand = 100,
#         match = 100 - 0.5 x sum |difference|, so 80 means 20 % of the soil would have to be swapped.
# Soil = FAO DSMW topsoil, 1:5,000,000, dominant soil per unit: it shortlists regions, it does not
# replace testing the local soil. Texture only (no clay mineralogy, climate or additives).
# ============================================================================
import json
import os

import scriptcontext as sc
import Rhino.Geometry as rg
from System.Drawing import Color

min_match = globals().get("min_match")
scale = globals().get("scale")
only_matching = globals().get("only_matching")
min_m = float(min_match) if min_match is not None else 80.0
k = float(scale) if scale else 1.0

# colour bands, same as the catalogue app: (lower bound, R, G, B)
BANDS = [(90, 26, 127, 55), (80, 76, 175, 80), (70, 192, 216, 74), (60, 240, 180, 41), (-1, 231, 229, 228)]

meshes, colors, outlines, match, country, texture = [], [], [], [], [], []
countries, country_area_km2, country_best = [], [], []
recipe, report = None, ""


def three(c, s, a):
    """rescale clay/silt/sand to sum to 100"""
    tot = float(c) + float(s) + float(a)
    if tot <= 0:
        return None
    return (c * 100.0 / tot, s * 100.0 / tot, a * 100.0 / tot)


def band_color(m):
    for lo, r, g, b in BANDS:
        if m >= lo:
            return Color.FromArgb(r, g, b)


def load_soil_map(path):
    """parsed GeoJSON, kept in memory until the file changes (it is ~6 MB)"""
    key = "earth_soil_map"
    stamp = (path, os.path.getmtime(path))
    hit = sc.sticky.get(key)
    if hit and hit[0] == stamp:
        return hit[1]
    with open(path, "r") as f:
        data = json.load(f)
    sc.sticky[key] = (stamp, data)
    return data


def rings(geom):
    """outer rings of a Polygon / MultiPolygon (holes are skipped: lakes inside a soil area)"""
    if geom["type"] == "Polygon":
        return [geom["coordinates"][0]]
    if geom["type"] == "MultiPolygon":
        return [p[0] for p in geom["coordinates"]]
    return []


mats = json.loads(json_text).get("materials", []) if json_text else []
mat = next((m for m in mats if m.get("id") == str(material_id or "").strip()), None)
soil = (mat or {}).get("soil") or {}

if not json_text:
    report = "Connect json_text from component 1."
elif mat is None:
    report = "No material with id '%s'. Take an id from component 3." % material_id
elif not soil.get("match_ready"):
    report = "%s has no clay/silt/sand in its paper, so it cannot be matched to soils." % mat.get("name")
elif not soil_map or not os.path.exists(str(soil_map)):
    report = "soil_map file not found: %s\nBuild it with: python \"01_Soil Extraction/build_soil_map.py\"" % soil_map
else:
    recipe_t = three(soil["clay_pct"], soil["silt_pct"], soil["sand_pct"])
    recipe = "clay %.0f / silt %.0f / sand %.0f %%" % recipe_t
    by_country = {}
    for f in load_soil_map(str(soil_map))["features"]:
        p = f["properties"]
        site = three(p["clay"], p["silt"], p["sand"])
        if site is None:
            continue
        mt = 100.0 - 0.5 * sum(abs(a - b) for a, b in zip(recipe_t, site))
        if mt >= min_m:
            c = by_country.setdefault(p["country"], [0.0, 0.0])
            c[0] += p.get("sqkm") or 0
            c[1] = max(c[1], mt)
        elif only_matching:
            continue
        col = band_color(mt)
        for ring in rings(f["geometry"]):
            pl = rg.Polyline([rg.Point3d(x * k, y * k, 0) for x, y in ring])
            if pl.Count < 4:
                continue
            if not pl.IsClosed:
                pl.Add(pl[0])
            mesh = rg.Mesh.CreateFromClosedPolyline(pl)
            if mesh is None:
                continue
            meshes.append(mesh)
            colors.append(col)
            outlines.append(pl.ToPolylineCurve())
            match.append(round(mt, 1))
            country.append(p["country"])
            texture.append(p["texture"])

    ranked = sorted(by_country.items(), key=lambda kv: -kv[1][0])
    countries = [c for c, v in ranked]
    country_area_km2 = [round(v[0]) for c, v in ranked]
    country_best = [round(v[1], 1) for c, v in ranked]
    total = sum(country_area_km2)
    lines = ["%s  (%s)" % (mat.get("name"), ", ".join(mat.get("techniques") or [])),
             "Soil recipe (rescaled): " + recipe,
             "Buildable (match >= %.0f %%): %d countries, %.1f million km2" % (min_m, len(countries), total / 1e6)]
    lines += ["  %-28s %8.0fk km2   best %.0f %%" % (c, a / 1e3, b)
              for c, a, b in list(zip(countries, country_area_km2, country_best))[:10]]
    lines.append("%d areas drawn. Texture only (DSMW topsoil): shortlist regions, then test the local soil." % len(meshes))
    report = "\n".join(lines)
