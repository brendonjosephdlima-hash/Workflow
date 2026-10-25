# ============================================================================
# COMPONENT 2: DECODE
#
# Inputs   json_text  str  Item   <- from component 1
# Outputs  n, ids, names, techniques, methods_present,
#          clay, silt, sand, gravel, texture, soil_source, match_ready,
#          rho, lam, cp, fc, ff, verified, doi, year
#
# Every list is in the same order: item 7 of 'names' goes with item 7 of 'lam', 'fc', 'clay', ...
# A missing value comes out as null. 'techniques' is the construction-method tag(s), e.g. "3d_printed".
# ============================================================================
import json

data = json.loads(json_text) if json_text else {}
mats = data.get("materials", [])


def prop(m, k):
    return (m.get("properties") or {}).get(k)


def soil(m, k):
    return (m.get("soil") or {}).get(k)


n = len(mats)
ids = [m.get("id") for m in mats]
names = [m.get("name") for m in mats]
techniques = [", ".join(m.get("techniques") or []) for m in mats]

counts = {}
for m in mats:
    for t in (m.get("techniques") or []):
        counts[t] = counts.get(t, 0) + 1
methods_present = ["%s (%d)" % (t, counts[t]) for t in sorted(counts)]

clay = [soil(m, "clay_pct") for m in mats]
silt = [soil(m, "silt_pct") for m in mats]
sand = [soil(m, "sand_pct") for m in mats]
gravel = [soil(m, "gravel_pct") for m in mats]
texture = [soil(m, "texture_class") for m in mats]
soil_source = [soil(m, "source") for m in mats]
match_ready = [bool(soil(m, "match_ready")) for m in mats]

rho = [prop(m, "dry_density_kg_m3") for m in mats]
lam = [prop(m, "thermal_conductivity_W_mK") for m in mats]
cp = [prop(m, "specific_heat_J_kgK") for m in mats]
fc = [prop(m, "compressive_strength_MPa") for m in mats]
ff = [prop(m, "flexural_strength_MPa") for m in mats]

verified = [bool(m.get("fully_verified")) for m in mats]
doi = [(m.get("source") or {}).get("doi") for m in mats]
year = [(m.get("source") or {}).get("year") for m in mats]
