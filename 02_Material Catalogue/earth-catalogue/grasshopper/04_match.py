# ============================================================================
# COMPONENT 4: MATCH SITE SOIL TO CATALOGUE
#
# Inputs   json_text   str    Item   <- from component 1
#          method      str    Item   <- construction method (same Value List as component 3)
#          site_clay   float  Item   <- the region's soil, % clay      (from your soil extraction: clay1)
#          site_silt   float  Item   <- % silt                          (silt1)
#          site_sand   float  Item   <- % sand                          (sand1)
#          only_verified bool  Item (optional)  True = only fully audited records
#          min_match   float  Item (optional)  hide matches below this % (e.g. 60)
#          min_fc      float  Item (optional)  discard materials weaker than this compressive strength (MPa)
#          max_lambda  float  Item (optional)  discard materials more conductive than this (W/m.K)
#          top_n       int    Item (optional)  how many to return, default 5
#          domain      str    Item (optional)  "mechanical" (Karamba) or "thermal" (Honeybee): keep only materials
#                                              with the minimum data for that tool (see 06 / 07)
#          allow_estimates bool Item (optional) with domain: also accept materials complete only through estimates
# Outputs  best, names, ids, match_pct, correction, texture, soil_source, lam, fc, rho, verified, doi, report
#
# best        the COMPLETE record of the best match as JSON text (same format as the catalogue file,
#             plus a "match" block with match_pct, correction and your site soil). Feed it to
#             component 5 (05_decode_best.py) to get every property, the recipe, curing, source...
#             Component 2 also reads it. It is empty (null) when nothing matched.
#             The other outputs are lists for the top_n results, closest first, lined up by position.
#
# match_pct   100 = the site soil is identical to the soil recipe in the paper.
#             Both soils are rescaled to clay+silt+sand = 100. The match is the share of the soil
#             that already agrees, so 60 means 40 % of the soil would have to be swapped.
#             Gravel is ignored. It compares soil texture only, not clay mineralogy or additives
#             (fibre, stabiliser, water), so use it to shortlist and then read the paper.
# correction  what to do to the site soil to reach that recipe, in percentage points of the soil,
#             e.g. "clay +3 / silt -10 / sand +7" (+ = needs more of it, - = needs less).
# ============================================================================
import json

# optional inputs may not exist on the component, or may be unconnected
only_verified = globals().get("only_verified")
min_match = globals().get("min_match")
min_fc = globals().get("min_fc")
max_lambda = globals().get("max_lambda")
top_n = globals().get("top_n")
domain = globals().get("domain")
allow_estimates = globals().get("allow_estimates")

data = json.loads(json_text) if json_text else {}
mats = data.get("materials", [])


def norm(t):
    return str(t or "").strip().lower().replace(" ", "_").replace("-", "_").replace("/", "_")


def three(c, s, a):
    """rescale clay/silt/sand to sum to 100"""
    tot = float(c) + float(s) + float(a)
    if tot <= 0:
        return None
    return (c * 100.0 / tot, s * 100.0 / tot, a * 100.0 / tot)


def prop(m, k):
    return (m.get("properties") or {}).get(k)


best, names, ids, match_pct, correction, texture, soil_source = None, [], [], [], [], [], []
lam, fc, rho, verified, doi = [], [], [], [], []
report = ""

site = None
if site_clay is not None and site_silt is not None and site_sand is not None:
    site = three(site_clay, site_silt, site_sand)

if not mats:
    report = "No catalogue loaded. Press the fetch button in component 1."
elif site is None:
    report = "Give the site's clay, silt and sand percentages."
else:
    want = norm(method)
    if want in ("", "all", "any"):
        want = None
    n_top = int(top_n) if top_n else 5
    dom = norm(domain) or None
    ok_levels = ("ready", "estimated") if allow_estimates else ("ready",)
    drops = {"other method": 0, "not %s data" % dom: 0, "%s data incomplete" % dom: 0, "no soil data": 0,
             "not verified": 0, "too weak": 0, "too conductive": 0, "below min match": 0}
    scored = []
    no_soil_names = []    # right method, but the paper gave no clay/silt/sand
    for m in mats:
        if want and want not in [norm(t) for t in (m.get("techniques") or [])]:
            drops["other method"] += 1
            continue
        if dom:
            r = (m.get("readiness") or {}).get(dom)
            if not r:
                drops["not %s data" % dom] += 1
                continue
            if r.get("level") not in ok_levels:
                drops["%s data incomplete" % dom] += 1
                continue
        s = m.get("soil") or {}
        if not s.get("match_ready"):
            drops["no soil data"] += 1
            no_soil_names.append(m.get("name"))
            continue
        if only_verified and not m.get("fully_verified"):
            drops["not verified"] += 1
            continue
        v_fc, v_lam = prop(m, "compressive_strength_MPa"), prop(m, "thermal_conductivity_W_mK")
        if min_fc is not None and (v_fc is None or v_fc < min_fc):
            drops["too weak"] += 1
            continue
        if max_lambda is not None and (v_lam is None or v_lam > max_lambda):
            drops["too conductive"] += 1
            continue
        t = three(s["clay_pct"], s["silt_pct"], s["sand_pct"])
        if t is None:
            drops["no soil data"] += 1
            no_soil_names.append(m.get("name"))
            continue
        delta = [a - b for a, b in zip(t, site)]            # change needed: site soil -> recipe soil
        match = 100.0 - 0.5 * sum(abs(x) for x in delta)    # 100 = identical
        if min_match is not None and match < min_match:
            drops["below min match"] += 1
            continue
        scored.append((match, delta, m))
    scored.sort(key=lambda x: -x[0])
    scored = scored[:n_top]

    names = [m.get("name") for mt, dl, m in scored]
    ids = [m.get("id") for mt, dl, m in scored]
    match_pct = [round(mt, 1) for mt, dl, m in scored]
    correction = ["clay %+d / silt %+d / sand %+d" % tuple(int(round(x)) for x in dl) for mt, dl, m in scored]
    texture = [(m.get("soil") or {}).get("texture_class") for mt, dl, m in scored]
    soil_source = [(m.get("soil") or {}).get("source") for mt, dl, m in scored]
    lam = [prop(m, "thermal_conductivity_W_mK") for mt, dl, m in scored]
    fc = [prop(m, "compressive_strength_MPa") for mt, dl, m in scored]
    rho = [prop(m, "dry_density_kg_m3") for mt, dl, m in scored]
    verified = [bool(m.get("fully_verified")) for mt, dl, m in scored]
    doi = [(m.get("source") or {}).get("doi") for mt, dl, m in scored]
    if scored:
        rec = dict(scored[0][2])
        rec["match"] = {"match_pct": match_pct[0], "correction": correction[0],
                        "site_clay": round(site[0], 1), "site_silt": round(site[1], 1), "site_sand": round(site[2], 1),
                        "method": want or "all"}
        best = json.dumps({"schema": data.get("schema"), "version": data.get("version"),
                           "count": 1, "materials": [rec]}, ensure_ascii=False)

    lines = ["Site soil (rescaled): clay %.0f / silt %.0f / sand %.0f %%" % site,
             "Method: %s" % (want or "all")]
    if dom:
        lines.append("Domain: %s (%s)" % (dom, "ready or estimated" if allow_estimates else "ready only"))
    if scored:
        lines.append("Best: %s, %.0f%% match" % (names[0], match_pct[0]))
        lines.append("To reach its soil: %s (points of the soil)" % correction[0])
        if any(s_ == "computed_from_composition" for s_ in soil_source):
            lines.append("Note: some soil values were computed from the recipe, not measured soil. Check the source paper.")
    else:
        lines.append("No candidates left.")
    if no_soil_names:
        lines.append("%d material(s) use this method but have no soil composition, so they cannot be matched "
                     "(see component 3): %s" % (len(no_soil_names), "; ".join(str(n) for n in no_soil_names)))
    lines.append("Left out: " + ", ".join("%d %s" % (v, k) for k, v in drops.items() if v) if any(drops.values()) else "Nothing left out.")
    report = "\n".join(lines)
