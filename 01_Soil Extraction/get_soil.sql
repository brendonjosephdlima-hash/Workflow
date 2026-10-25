CREATE OR REPLACE FUNCTION get_soil(lat double precision, lon double precision)
RETURNS json
LANGUAGE sql
AS $$
  SELECT row_to_json(t) FROM (
    SELECT g."SNUM", g."FAOSOIL", g."DOMSOI", g."CNTNAME", g."COUNTRY",
           a."SNAM", a."TEXTURE", a."HYDGRP",
           a."SOL_BD1", a."SOL_AWC1", a."SOL_K1",
           a."CLAY1", a."SILT1", a."SAND1"
    FROM global_soils g
    LEFT JOIN soil_attributes a ON a."SNUM" = g."SNUM"
    WHERE st_intersects(g.geometry, st_setsrid(st_point(lon, lat), 4326))
    LIMIT 1
  ) t;
$$;