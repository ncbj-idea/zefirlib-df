-- Safe version of get_gis_data_for_given_terc using ST_Distance instead of KNN
-- This function is slower but guarantees correct ordering of nearest neighbors
-- Used as fallback when KNN ordering validation fails
DROP FUNCTION IF EXISTS get_gis_data_for_given_terc_safe;
CREATE OR REPLACE FUNCTION get_gis_data_for_given_terc_safe(terc_code varchar) RETURNS TABLE (
        id int,
        identyfikator varchar,
        funkcja_ogolna varchar,
        funkcja_szczegolowa varchar [],
        pow_obrysu_m2 numeric,
        liczba_kondygnacji int,
        pow_uzytkowa_m2 numeric,
        czy_ogrzewany bool,
        czy_zabytek bool,
        other jsonb,
        kategoria_istnienia text,
        geom geometry(MultiPolygon, 2180),
        miejscowosc varchar,
        ulica varchar,
        numer_porzadkowy varchar,
        kod_pocztowy varchar,
        longitude_addr double precision,
        latitude_addr double precision,
        longitude_centroid double precision,
        latitude_centroid double precision,
        addr_distance numeric,
        gas_distance numeric,
        heat_distance numeric,
        heat_connected bool,
        gas_connected bool
    ) LANGUAGE plpgsql AS $$
DECLARE boundary_geometry geometry;
-- Administrative boundary geometry for the given TERC
BEGIN -- Retrieve the most recent administrative boundary geometry for the given TERC code
SELECT adm.geom INTO boundary_geometry
FROM administrative_boundary adm
WHERE adm.terc = terc_code
    AND adm.import_id = (
        SELECT MAX(import_id)
        FROM administrative_boundary
        WHERE terc = terc_code
    );
-- Return the processed building data with spatial joins using ST_Distance for guaranteed ordering
RETURN QUERY WITH -- Process BDOT10k building data within the administrative boundary, filtered to heated buildings only
buildings_with_calculations AS (
    SELECT b.*,
        -- Extract existence category from JSON metadata
        b.other->>'x_katistnienia' AS kategoria_istnienia,
        -- Calculate outline area in square meters
        ROUND(ST_Area(b.geom)::numeric, 2) AS pow_obrysu_m2,
        -- Calculate usable area (outline area * number of floors)
        ROUND(
            (ST_Area(b.geom) * b.liczba_kondygnacji::FLOAT)::numeric,
            2
        ) AS pow_uzytkowa_m2,
        true AS czy_ogrzewany
    FROM bdot10k b
    WHERE ST_Contains(boundary_geometry, b.geom)
        -- Filter to heated buildings only using EXISTS (more efficient than array overlap)
        AND EXISTS (
            SELECT 1
            FROM dict_funkcja_szczegolowa d
            WHERE d.czy_ogrzewany
                AND b.funkcja_szczegolowa @> ARRAY[d.kod::varchar]
        )
),
-- Get address points within the administrative boundary
address_points AS (
    SELECT *
    FROM address_point a
    WHERE ST_Contains(boundary_geometry, a.geom)
),
-- Join buildings with their nearest address points using ST_Distance for guaranteed ordering
buildings_with_addresses AS (
    SELECT b.*,
        addr_join.miejscowosc,
        addr_join.ulica,
        addr_join.numer_porzadkowy,
        addr_join.kod_pocztowy,
        addr_join.longitude,
        addr_join.latitude,
        addr_join.distance_to_building AS addr_distance
    FROM buildings_with_calculations b
        LEFT JOIN LATERAL (
            SELECT addr.*,
                ROUND(ST_Distance(addr.geom, b.geom)::numeric, 3) AS distance_to_building
            FROM address_points addr
            WHERE ST_DWithin(addr.geom, b.geom, 200) -- Pre-filter to 200m radius to reduce distance calculations
            ORDER BY ST_Distance(addr.geom, b.geom) ASC -- Explicit distance ordering (safe but slower)
            LIMIT 1
        ) AS addr_join ON true
),
-- Get heating infrastructure tiles within the boundary (layer 3 = heat)
heating_infrastructure AS (
    SELECT tile.*
    FROM tile
    WHERE tile.layer = 3
        AND ST_Contains(boundary_geometry, tile.geom)
),
-- Get gas infrastructure tiles within the boundary (layer 4 = gas)
gas_infrastructure AS (
    SELECT tile.*
    FROM tile
    WHERE tile.layer = 4
        AND ST_Contains(boundary_geometry, tile.geom)
),
-- Join buildings with nearest heat and gas infrastructure using ST_Distance for guaranteed ordering
buildings_with_infrastructure AS (
    SELECT b.*,
        COALESCE(ROUND(gas_join.distance_to_gas::numeric, 3), NULL) AS gas_distance,
        COALESCE(ROUND(heat_join.distance_to_heat::numeric, 3), NULL) AS heat_distance,
        -- Building is considered heat-connected if within 10 meters
        COALESCE(heat_join.distance_to_heat <= 10, false) AS heat_connected,
        -- Building is considered gas-connected if within 10 meters
        COALESCE(gas_join.distance_to_gas <= 10, false) AS gas_connected
    FROM buildings_with_addresses b
        LEFT JOIN LATERAL (
            SELECT ST_Distance(gas.geom, b.geom) AS distance_to_gas
            FROM gas_infrastructure gas
            WHERE ST_DWithin(gas.geom, b.geom, 20) -- Pre-filter to 20m radius to reduce distance calculations
            ORDER BY ST_Distance(gas.geom, b.geom) ASC -- Explicit distance ordering (safe but slower)
            LIMIT 1
        ) AS gas_join ON true
        LEFT JOIN LATERAL (
            SELECT ST_Distance(heat.geom, b.geom) AS distance_to_heat
            FROM heating_infrastructure heat
            WHERE ST_DWithin(heat.geom, b.geom, 20) -- Pre-filter to 20m radius to reduce distance calculations
            ORDER BY ST_Distance(heat.geom, b.geom) ASC -- Explicit distance ordering (safe but slower)
            LIMIT 1
        ) AS heat_join ON true
) -- Final selection - return only heated buildings
SELECT b.id,
    b.identyfikator,
    b.funkcja_ogolna,
    b.funkcja_szczegolowa,
    b.pow_obrysu_m2,
    b.liczba_kondygnacji,
    b.pow_uzytkowa_m2,
    b.czy_ogrzewany,
    b.czy_zabytek,
    b.other,
    b.kategoria_istnienia,
    b.geom,
    b.miejscowosc,
    b.ulica,
    b.numer_porzadkowy,
    b.kod_pocztowy,
    b.longitude AS longitude_addr,
    b.latitude AS latitude_addr,
    -- Calculate centroid coordinates in WGS84 (EPSG:4326)
    ST_X(ST_Transform(ST_Centroid(b.geom), 4326)) AS longitude_centroid,
    ST_Y(ST_Transform(ST_Centroid(b.geom), 4326)) AS latitude_centroid,
    b.addr_distance,
    b.gas_distance,
    b.heat_distance,
    b.heat_connected,
    b.gas_connected
FROM buildings_with_infrastructure b;
END;
$$;
