# ============================================================================
# COMPONENT 6: KARAMBA MATERIAL FROM THE BEST MATCH  (mechanical domain)
#
# Inputs   best             str    Item   <- the 'best' output of component 4 (use domain = "mechanical" there)
#          nu               float  Item (optional)  Poisson's ratio to ASSUME when the paper gives none, default 0.2
#          allow_estimates  bool   Item (optional)  True = also use values the catalogue only estimated
# Outputs  name, E, G, gamma, alphaT, ft, fc, ready, assumptions, report
#
# Wire into Karamba's material component (Karamba units):
#   E       Young's modulus      kN/cm2   = elastic modulus MPa / 10
#   G       shear modulus        kN/cm2   = E / (2 (1 + nu)), nu from the paper if reported, else the assumed nu
#   gamma   specific weight      kN/m3    = dry density kg/m3 x 9.81 / 1000
#   alphaT  thermal expansion    1/C      not in the catalogue (earth papers almost never report it): always null.
#                                         Only matters for temperature loads; otherwise leave Karamba's input empty.
#   ft      tensile strength     kN/cm2   = tensile strength MPa / 10, null if not reported
#   fc      compressive strength kN/cm2   = compressive strength MPa / 10 (positive; older Karamba with a single
#                                         'fy' input: use fc. If your Karamba version expects fc negative, use -fc)
#
# ready = E, fc and gamma all come from the paper (reported or calculated from its data).
# assumptions lists every value that does not come from the paper. Never wire a null into Karamba.
# ============================================================================
import json

nu_in = globals().get("nu")
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
E_mpa, fc_mpa, ft_mpa = get("elastic_modulus_MPa"), get("compressive_strength_MPa"), get("tensile_strength_MPa")
rho = get("dry_density_kg_m3")
nu_paper = get("poisson_ratio")

E = round(E_mpa / 10.0, 3) if E_mpa is not None else None
fc = round(fc_mpa / 10.0, 4) if fc_mpa is not None else None
ft = round(ft_mpa / 10.0, 4) if ft_mpa is not None else None
gamma = round(rho * 9.81 / 1000.0, 3) if rho is not None else None
alphaT = None

if nu_paper is not None:
    nu_used = nu_paper
else:
    nu_used = float(nu_in) if nu_in is not None else 0.2
    if E is not None:
        assumptions.append("Poisson's ratio %.2f ASSUMED (not reported), used for G" % nu_used)
G = round(E / (2.0 * (1.0 + nu_used)), 3) if E is not None else None

ready = rec is not None and None not in (E, fc, gamma) and not any(
    B.get(k) == "estimated" for k in ("elastic_modulus_MPa", "compressive_strength_MPa", "dry_density_kg_m3"))

lines = []
if rec is None:
    lines.append("No material. Connect the 'best' output of component 4.")
else:
    r = ((rec.get("readiness") or {}).get("mechanical") or {})
    lines.append("%s  (catalogue: mechanical %s)" % (name, r.get("level", "no mechanical data")))
    for label, v, unit in (("E", E, "kN/cm2"), ("G", G, "kN/cm2"), ("gamma", gamma, "kN/m3"),
                           ("ft", ft, "kN/cm2"), ("fc", fc, "kN/cm2")):
        lines.append("  %-6s %s" % (label, "%s %s" % (v, unit) if v is not None else "MISSING"))
    lines.append("  alphaT not reported: leave Karamba's input empty unless you apply temperature loads")
    if ft is None:
        lines.append("  ft not reported: earth carries almost no tension; set it yourself if your analysis needs it")
    lines.append("READY for Karamba" if ready else
                 ("Usable for Karamba WITH estimates" if None not in (E, fc, gamma) else "NOT ready: E, fc and gamma are all needed"))
    if assumptions:
        lines.append("Assumptions:")
        lines.extend("  - " + a for a in assumptions)
report = "\n".join(lines)
