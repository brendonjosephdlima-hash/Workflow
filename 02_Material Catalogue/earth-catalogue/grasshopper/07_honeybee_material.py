# ============================================================================
# COMPONENT 7: HONEYBEE MATERIAL FROM THE BEST MATCH  (thermal domain)
#
# Inputs   best             str    Item   <- the 'best' output of component 4 (use domain = "thermal" there)
#          thickness        float  Item   wall layer thickness in METRES (your design, not from the paper)
#          cp               float  Item (optional)  specific heat J/kgK to ASSUME when the paper gives none
#          allow_estimates  bool   Item (optional)  True = also use values the catalogue only estimated
# Outputs  name, thickness_m, conductivity, density, spec_heat, ready, assumptions, report, material
#
# Wire name, thickness_m, conductivity, density, spec_heat into Honeybee's "HB Opaque Material" component
# (_name_, _thickness, _conductivity, _density, _spec_heat). Units are already Honeybee's: m, W/m-K, kg/m3, J/kg-K.
# 'material' is a ready Honeybee EnergyMaterial when the honeybee-energy library can be imported here
# (otherwise null: use the HB Opaque Material component as above).
#
# ready = conductivity, density and specific heat all come from the paper (reported or calculated from its data,
# e.g. cp = conductivity / (density x diffusivity)). assumptions lists every value that does not.
# ============================================================================
import json
import re

cp_in = globals().get("cp")
allow_estimates = globals().get("allow_estimates")

rec = None
if best:
    d = json.loads(best)
    if isinstance(d, dict) and d.get("materials"):
        rec = d["materials"][0]
    elif isinstance(d, dict) and "name" in d:
        rec = d

P = (rec or {}).get("properties") or {}
B = (rec or {}).get("property_basis") or {}
OK = ("reported", "manual", "derived", "estimated") if allow_estimates else ("reported", "manual", "derived")
assumptions = []


def get(k):
    """value only if its basis is acceptable; estimated values are noted"""
    v = P.get(k)
    if v is None or B.get(k, "reported") not in OK:
        return None
    if B.get(k) == "estimated":
        assumptions.append("%s is an ESTIMATE, not from the paper" % k)
    return v


name = (rec or {}).get("name")
conductivity = get("thermal_conductivity_W_mK")
density = get("dry_density_kg_m3")
spec_heat = get("specific_heat_J_kgK")
from_paper = (None not in (conductivity, density, spec_heat) and not any(
    B.get(k) == "estimated" for k in ("thermal_conductivity_W_mK", "dry_density_kg_m3", "specific_heat_J_kgK")))
if spec_heat is None and cp_in is not None:
    spec_heat = float(cp_in)
    assumptions.append("specific heat %.0f J/kgK ASSUMED (your cp input), not from the paper" % spec_heat)
thickness_m = float(thickness) if thickness else None

ready = rec is not None and from_paper and thickness_m is not None

material = None
if rec is not None and None not in (conductivity, density, spec_heat, thickness_m):
    try:
        from honeybee_energy.material.opaque import EnergyMaterial
        ident = re.sub(r"[^A-Za-z0-9_\-]", "_", "%s_%s" % ((rec.get("id") or "earth"), name or ""))[:100]
        material = EnergyMaterial(ident, thickness_m, conductivity, density, spec_heat)
        material.display_name = name
    except ImportError:
        material = None

lines = []
if rec is None:
    lines.append("No material. Connect the 'best' output of component 4.")
else:
    r = ((rec.get("readiness") or {}).get("thermal") or {})
    lines.append("%s  (catalogue: thermal %s)" % (name, r.get("level", "no thermal data")))
    for label, v, unit in (("thickness", thickness_m, "m"), ("conductivity", conductivity, "W/m-K"),
                           ("density", density, "kg/m3"), ("spec_heat", spec_heat, "J/kg-K")):
        lines.append("  %-12s %s" % (label, "%s %s" % (v, unit) if v is not None else "MISSING"))
    if thickness_m is None:
        lines.append("  give the wall thickness in metres")
    if spec_heat is None:
        lines.append("  no specific heat in the paper: give a cp input (it will be listed as an assumption)")
    lines.append("READY for Honeybee" if ready else
                 ("Usable for Honeybee WITH assumptions" if None not in (conductivity, density, spec_heat, thickness_m)
                  else "NOT ready"))
    if assumptions:
        lines.append("Assumptions:")
        lines.extend("  - " + a for a in assumptions)
    if material is None and None not in (conductivity, density, spec_heat, thickness_m):
        lines.append("(honeybee-energy not importable here: wire the outputs into HB Opaque Material)")
report = "\n".join(lines)
