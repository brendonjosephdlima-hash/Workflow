# ============================================================================
# COMPONENT 5: DECODE THE BEST MATCH  ->  mechanical + thermal properties
#
# Input    best  str  Item   <- the 'best' output of component 4
#
# Outputs  each one is a single value (not a list), because it is one material. null = not reported in the paper.
#
#   WHICH        name, id, techniques, match_pct, correction, verified, doi
#   MECHANICAL   fc    compressive strength, MPa     ft   tensile strength, MPa
#                ff    flexural strength, MPa        E    elastic modulus, MPa
#   THERMAL      lam   conductivity, W/mK            cp   specific heat, J/kgK
#                alpha diffusivity, mm2/s            vhc  volumetric heat capacity, MJ/m3K
#                dec   decrement factor, -           lag  time lag, h
#   PHYSICAL     rho   dry density, kg/m3            por  porosity, %
#   HYGRIC       shr   drying shrinkage, %           wabs water absorption, %
#   SOIL         clay, silt, sand, gravel (% of the material's own soil), texture
#   CHECK        missing   the mechanical/thermal/physical properties that have no value for this material
#
# Poisson's ratio is not stored in the catalogue, so it is not available here.
# ============================================================================
import json

rec = None
if best:
    d = json.loads(best)
    if isinstance(d, dict) and d.get("materials"):
        rec = d["materials"][0]
    elif isinstance(d, dict) and "name" in d:
        rec = d

P = (rec or {}).get("properties") or {}
S = (rec or {}).get("soil") or {}
M = (rec or {}).get("match") or {}
SRC = (rec or {}).get("source") or {}

# ---- which
name = (rec or {}).get("name")
id = (rec or {}).get("id")
techniques = ", ".join((rec or {}).get("techniques") or [])
match_pct = M.get("match_pct")
correction = M.get("correction")
verified = bool((rec or {}).get("fully_verified"))
doi = SRC.get("doi")

# ---- mechanical
fc = P.get("compressive_strength_MPa")
ft = P.get("tensile_strength_MPa")
ff = P.get("flexural_strength_MPa")
E = P.get("elastic_modulus_MPa")

# ---- thermal
lam = P.get("thermal_conductivity_W_mK")
cp = P.get("specific_heat_J_kgK")
alpha = P.get("thermal_diffusivity_mm2_s")
vhc = P.get("volumetric_heat_capacity_MJ_m3K")
dec = P.get("decrement_factor")
lag = P.get("time_lag_h")

# ---- physical / hygric
rho = P.get("dry_density_kg_m3")
por = P.get("porosity_pct")
shr = P.get("shrinkage_pct")
wabs = P.get("water_absorption_pct")

# ---- soil
clay, silt, sand, gravel = S.get("clay_pct"), S.get("silt_pct"), S.get("sand_pct"), S.get("gravel_pct")
texture = S.get("texture_class")

# ---- which of the analysis properties are empty
wanted = [("fc", fc), ("ft", ft), ("ff", ff), ("E", E), ("lam", lam), ("cp", cp), ("alpha", alpha),
          ("vhc", vhc), ("dec", dec), ("lag", lag), ("rho", rho), ("por", por)]
missing = [k for k, v in wanted if v is None] if rec else ["No best match. Connect the 'best' output of component 4."]
