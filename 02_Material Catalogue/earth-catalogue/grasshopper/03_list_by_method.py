# ============================================================================
# COMPONENT 3: LIST BY CONSTRUCTION METHOD
#
# Inputs   json_text  str  Item   <- from component 1
#          method     str  Item   <- from a Value List (see README): 3d_printed, cob, adobe, rammed_earth,
#                                    compressed_earth_block, cast_earth, wattle_and_daub, earthbag, other
#                                    leave empty or use "all" for no filter
#          only_verified  bool Item (optional)  True = only fully audited records
# Outputs  count, names, ids, techniques, lam, fc, rho, clay, silt, sand, match_ready, verified, doi, report
# ============================================================================
import json

# optional inputs may not exist on the component, or may be unconnected
only_verified = globals().get("only_verified")

data = json.loads(json_text) if json_text else {}
mats = data.get("materials", [])


def norm(t):
    return str(t or "").strip().lower().replace(" ", "_").replace("-", "_").replace("/", "_")


want = norm(method)
if want in ("", "all", "any"):
    want = None

picked = []
for m in mats:
    if want and want not in [norm(t) for t in (m.get("techniques") or [])]:
        continue
    if only_verified and not m.get("fully_verified"):
        continue
    picked.append(m)


def prop(m, k):
    return (m.get("properties") or {}).get(k)


def soil(m, k):
    return (m.get("soil") or {}).get(k)


count = len(picked)
names = [m.get("name") for m in picked]
ids = [m.get("id") for m in picked]
techniques = [", ".join(m.get("techniques") or []) for m in picked]
lam = [prop(m, "thermal_conductivity_W_mK") for m in picked]
fc = [prop(m, "compressive_strength_MPa") for m in picked]
rho = [prop(m, "dry_density_kg_m3") for m in picked]
clay = [soil(m, "clay_pct") for m in picked]
silt = [soil(m, "silt_pct") for m in picked]
sand = [soil(m, "sand_pct") for m in picked]
match_ready = [bool(soil(m, "match_ready")) for m in picked]
verified = [bool(m.get("fully_verified")) for m in picked]
doi = [(m.get("source") or {}).get("doi") for m in picked]

if not mats:
    report = "No catalogue loaded. Press the fetch button in component 1."
else:
    report = "%s: %d of %d materials%s. %d have a soil composition usable for matching, %d are fully verified." % (
        want or "all methods", count, len(mats), " (verified only)" if only_verified else "",
        sum(match_ready), sum(verified))
    if want and count == 0:
        present = sorted(set(norm(t) for m in mats for t in (m.get("techniques") or [])))
        report += " Methods in this catalogue: " + ", ".join(present)
