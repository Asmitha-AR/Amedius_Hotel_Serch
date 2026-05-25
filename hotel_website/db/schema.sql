-- Master country list pulled from TBO Country API.
CREATE TABLE IF NOT EXISTS tbo_countries (
    country_code TEXT PRIMARY KEY,
    country_name TEXT NOT NULL,
    fetched_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- All TBO cities (every TBO city, regardless of whether Amadeus has it).
CREATE TABLE IF NOT EXISTS tbo_cities (
    tbo_city_code TEXT PRIMARY KEY,
    city_name     TEXT NOT NULL,
    country_code  TEXT NOT NULL REFERENCES tbo_countries(country_code) ON DELETE CASCADE,
    fetched_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_tbo_cities_country ON tbo_cities(country_code);

-- TBO city ↔ Amadeus/IATA city mapping. Populated via Amadeus or Gemini resolution.
-- iata_city_code may be NULL until a resolver finds a match.
CREATE TABLE IF NOT EXISTS city_cd_mapping (
    tbo_city_code   TEXT PRIMARY KEY REFERENCES tbo_cities(tbo_city_code) ON DELETE CASCADE,
    iata_city_code  TEXT,
    city_name       TEXT NOT NULL,
    country_code    TEXT NOT NULL,
    resolver_source TEXT,            -- 'amadeus' | 'gemini' | 'manual'
    resolved_at     TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_city_cd_mapping_iata ON city_cd_mapping(iata_city_code);

-- Hotel ID mapping: TBO hotel ↔ Amadeus hotel.
CREATE TABLE IF NOT EXISTS hotel_id_mapping (
    id                  BIGSERIAL PRIMARY KEY,
    tbo_hotel_code      TEXT NOT NULL,
    amadeus_hotel_id    TEXT NOT NULL,
    tbo_hotel_name      TEXT,
    amadeus_hotel_name  TEXT,
    iata_city_code      TEXT,
    name_score          NUMERIC(5,4),
    distance_meters     NUMERIC(8,2),
    combined_score      NUMERIC(5,4),
    matched_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tbo_hotel_code, amadeus_hotel_id)
);
CREATE INDEX IF NOT EXISTS idx_hotel_mapping_tbo ON hotel_id_mapping(tbo_hotel_code);
CREATE INDEX IF NOT EXISTS idx_hotel_mapping_amadeus ON hotel_id_mapping(amadeus_hotel_id);
CREATE INDEX IF NOT EXISTS idx_hotel_mapping_city ON hotel_id_mapping(iata_city_code);
