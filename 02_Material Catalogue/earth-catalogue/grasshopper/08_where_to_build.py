# ============================================================================
# COMPONENT 8: WHERE CAN I BUILD THIS?  (reverse of component 4: material -> world map of matching soils)
#
# Inputs   json_text    str    Item   <- from component 1
#          material_id  str    Item   <- an id from component 3 (List Item on its 'ids'), e.g. "EM-..."
#          soil_map     str    Item (optional)  full path to data/soil_map.geojson; empty = SOIL_MAP_PATH below.
#                                        Made once with:  python "01_Soil Extraction/build_soil_map.py"
#          min_match    float  Item (optional)  areas at or above this count as buildable, default 80
#          scale        float  Item (optional)  model units per degree, default 1 (x = longitude, y = latitude)
#          only_matching bool  Item (optional)  True = draw only areas >= min_match (cleaner)
#          show_outlines bool  Item (optional)  True = also output every area boundary (slow: ~30,000 curves)
#          climate_filter str  Item (optional)  Koppen-Geiger classes to keep, by code or prefix, comma separated:
#                                        "B" = all arid, "BWh, BSh" = hot desert + hot steppe, "Cs" = Mediterranean.
#                                        Areas in other climates are not counted and are drawn pale ("other climate").
#                                        Empty = all climates.
# Outputs  meshes, colors     one joined mesh per colour band, at most 5 (Custom Preview: meshes -> G, colors -> M)
#          legend             the band of each mesh, e.g. "90+ %"  (Legend component: colors -> C, legend -> T)
#          borders            country outlines, always drawn (from countries.geojson next to soil_map)
#          outlines           area boundaries as closed polylines (only with show_outlines), same order as match
#          match, country, region, texture, climate   per drawn area (region = main state / province / department,
#                                                      climate = main Koppen-Geiger class 1991-2020, e.g. "Csa")
#          climates, climate_area_km2   climate classes of the buildable areas, largest first (use them to pick a filter)
#          countries, country_area_km2, country_best   countries ranked by buildable area (>= min_match)
#          regions, region_area_km2, region_best       TREES: branch {i} = the buildable regions of countries[i],
#                                                      largest first (regions from Natural Earth admin-1)
#          recipe, report
#
# Match = same score as component 4: both soils rescaled to clay+silt+sand = 100,
#         match = 100 - 0.5 x sum |difference|, so 80 means 20 % of the soil would have to be swapped.
# Soil = FAO DSMW topsoil, 1:5,000,000, dominant soil per unit: it shortlists regions, it does not
# replace testing the local soil. Texture only (no clay mineralogy or additives).
# Climate = Beck et al. (2023) Koppen-Geiger 1991-2020, Scientific Data 10, 724 (CC BY 4.0): cite it when used.
# ============================================================================
import json
import os
import re

import ghpythonlib.treehelpers as th
import scriptcontext as sc
import Rhino.Geometry as rg
from System.Collections.Generic import List
from System.Drawing import Color

SOIL_MAP_PATH = r"C:\Users\Asus\Desktop\MAA 02\Thesis\Workflow\02_Material Catalogue\earth-catalogue\data\soil_map.geojson"

soil_map = str(globals().get("soil_map") or "").strip() or SOIL_MAP_PATH
min_match = globals().get("min_match")
scale = globals().get("scale")
only_matching = globals().get("only_matching")
show_outlines = globals().get("show_outlines")
climate_filter = globals().get("climate_filter")
min_m = float(min_match) if min_match is not None else 80.0
k = float(scale) if scale else 1.0
clim_keep = [t.lower() for t in re.split(r"[,;\s]+", str(climate_filter or "")) if t]

# colour bands, same as the catalogue app: (lower bound, R, G, B, label); the last one holds areas
# outside climate_filter
BANDS = [(90, 26, 127, 55, "90+ %"), (80, 76, 175, 80, "80-89 %"), (70, 192, 216, 74, "70-79 %"),
         (60, 240, 180, 41, "60-69 %"), (-1, 231, 229, 228, "< 60 %"), (None, 247, 247, 245, "other climate")]

meshes, colors, legend, borders, outlines, match, country, region, texture, climate = [], [], [], [], [], [], [], [], [], []
countries, country_area_km2, country_best, climates, climate_area_km2 = [], [], [], [], []
regions, region_area_km2, region_best = None, None, None
recipe, report = None, ""


def three(c, s, a):
    """rescale clay/silt/sand to sum to 100"""
    tot = float(c) + float(s) + float(a)
    if tot <= 0:
        return None
    return (c * 100.0 / tot, s * 100.0 / tot, a * 100.0 / tot)


def band_of(m):
    for i, b in enumerate(BANDS):
        if b[0] is not None and m >= b[0]:
            return i


def climate_ok(code):
    return not clim_keep or any(str(code or "").lower().startswith(t) for t in clim_keep)


def load_areas(path, k):
    """[(properties, clay/silt/sand rescaled, [(mesh, polyline), ...])] for every soil area.
    The geometry does not depend on the material, so it is built once and kept until the file or scale changes."""
    key = "earth_soil_areas"
    stamp = (path, os.path.getmtime(path), k)
    hit = sc.sticky.get(key)
    if hit and hit[0] == stamp:
        return hit[1]
    with open(path, "r") as f:
        data = json.load(f)
    areas = []
    for f in data["features"]:
        p = f["properties"]
        site = three(p["clay"], p["silt"], p["sand"])
        if site is None:
            continue
        parts = []
        for ring in rings(f["geometry"]):
            pl = rg.Polyline([rg.Point3d(x * k, y * k, 0) for x, y in ring])
            if pl.Count < 4:
                continue
            if not pl.IsClosed:
                pl.Add(pl[0])
            mesh = rg.Mesh.CreateFromClosedPolyline(pl)
            if mesh is not None:
                parts.append((mesh, pl))
        if parts:
            areas.append((p, site, parts))
    sc.sticky[key] = (stamp, areas)
    return areas


def load_borders(path, k):
    """country outlines as polyline curves, cached like the areas"""
    if not os.path.exists(path):
        return []
    key = "earth_country_borders"
    stamp = (path, os.path.getmtime(path), k)
    hit = sc.sticky.get(key)
    if hit and hit[0] == stamp:
        return hit[1]
    with open(path, "r") as f:
        data = json.load(f)
    curves = []
    for f in data["features"]:
        for ring in rings(f["geometry"]):
            if len(ring) >= 4:
                curves.append(rg.Polyline([rg.Point3d(x * k, y * k, 0) for x, y in ring]).ToPolylineCurve())
    sc.sticky[key] = (stamp, curves)
    return curves


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
    borders = load_borders(os.path.join(os.path.dirname(str(soil_map)), "countries.geojson"), k)
    by_country, by_climate = {}, {}
    per_band = [[] for b in BANDS]
    for p, site, parts in load_areas(str(soil_map), k):
        mt = 100.0 - 0.5 * sum(abs(a - b) for a, b in zip(recipe_t, site))
        in_climate = climate_ok(p.get("climate"))
        if mt >= min_m and in_climate:
            by_climate[p.get("climate") or "?"] = by_climate.get(p.get("climate") or "?", 0) + (p.get("sqkm") or 0)
            c = by_country.setdefault(p["country"], [0.0, 0.0, {}])
            c[0] += p.get("sqkm") or 0
            c[1] = max(c[1], mt)
            for name, km2 in p.get("regions") or []:
                rr = c[2].setdefault(name, [0.0, 0.0])
                rr[0] += km2
                rr[1] = max(rr[1], mt)
        elif only_matching:
            continue
        per_band[band_of(mt) if in_climate else len(BANDS) - 1].extend(m for m, pl in parts)
        match.append(round(mt, 1))
        country.append(p["country"])
        region.append(p["regions"][0][0] if p.get("regions") else "")
        texture.append(p["texture"])
        climate.append(p.get("climate") or "")
        if show_outlines:
            outlines.extend(pl.ToPolylineCurve() for m, pl in parts)
    n_drawn = len(match)

    # one joined mesh per band: a handful of objects for the preview instead of ~30,000
    for b, parts in zip(BANDS, per_band):
        if parts:
            joined = rg.Mesh()
            joined.Append(List[rg.Mesh](parts))
            meshes.append(joined)
            colors.append(Color.FromArgb(b[1], b[2], b[3]))
            legend.append(b[4])

    ranked = sorted(by_country.items(), key=lambda kv: -kv[1][0])
    countries = [c for c, v in ranked]
    country_area_km2 = [round(v[0]) for c, v in ranked]
    country_best = [round(v[1], 1) for c, v in ranked]
    reg = [sorted(v[2].items(), key=lambda kv: -kv[1][0]) for c, v in ranked]
    regions = th.list_to_tree([[n for n, rv in rs] for rs in reg])
    region_area_km2 = th.list_to_tree([[round(rv[0]) for n, rv in rs] for rs in reg])
    region_best = th.list_to_tree([[round(rv[1], 1) for n, rv in rs] for rs in reg])
    total = sum(country_area_km2)
    cl = sorted(by_climate.items(), key=lambda kv: -kv[1])
    climates = [c for c, a in cl]
    climate_area_km2 = [round(a) for c, a in cl]
    lines = ["%s  (%s)" % (mat.get("name"), ", ".join(mat.get("techniques") or [])),
             "Soil recipe (rescaled): " + recipe,
             "Climate filter: " + (", ".join(t for t in re.split(r"[,;\s]+", str(climate_filter)) if t) if clim_keep else "none (all climates)"),
             "Buildable (match >= %.0f %%): %d countries, %.1f million km2" % (min_m, len(countries), total / 1e6),
             "  climates: " + ", ".join("%s %.1fM km2" % (c, a / 1e6) for c, a in cl[:8])]
    for c, a, b, rs in list(zip(countries, country_area_km2, country_best, reg))[:10]:
        lines.append("  %-28s %8.0fk km2   best %.0f %%" % (c, a / 1e3, b))
        if rs:
            lines.append("      " + ", ".join("%s (%.0f %%)" % (n, rv[1]) for n, rv in rs[:5]) + (", ..." if len(rs) > 5 else ""))
    lines.append("%d areas drawn in %d colour bands. Texture only (DSMW topsoil): shortlist regions, then test the local soil."
                 % (n_drawn, len(meshes)))
    report = "\n".join(lines)
