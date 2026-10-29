# Sources, definitions and publication boundary

- NYC TLC trip records: https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page. Records come from technology providers; TLC does not warrant accuracy. Monthly public publication is delayed, so this historical simulation does not establish real-time availability.
-2024 Yellow Taxi Trip Data: https://data.cityofnewyork.us/Transportation/2024-Yellow-Taxi-Trip-Data/rwwi-khbc ; metadata https://data.cityofnewyork.us/api/views/rwwi-khbc.json. Published August21,2026, with corrections possible. Pickup time is meter engagement; pickup location is its TLC taxi zone.
- Zone facts: https://d37ci6vzurychx.cloudfront.net/misc/taxi_zone_lookup.csv (official TLC-linked lookup):132JFK Airport,138LaGuardia Airport, both Queens/Airports. Source CSV remains private; two attributed code/name facts may be retained.
- Dictionary: https://www.nyc.gov/assets/tlc/downloads/pdf/data_dictionary_trip_records_yellow.pdf. Full document/artwork excluded.
- Named stress dates: https://www.opm.gov/policy-data-oversight/pay-leave/federal-holidays/ ,2024 schedule, Thanksgiving November28 and Christmas December25.
- Query function definitions: https://dev.socrata.com/docs/functions/date_trunc_ymd.html and https://dev.socrata.com/docs/functions/date_extract_hh.html. Original query/code implementation; no copied documentation or licensed code.
- NYC Open Data overview: https://www.nyc.gov/opendata/get-started/what-is-open-data- ; NYC terms https://www.nyc.gov/main/terms-of-use. The package publishes minimal attributed factual aggregate derivatives and original analysis, not wholesale trip records, website content, logos or maps. No City endorsement or blanket public-domain claim.

Scope counts published records, not passengers, requests, unique deduplicated trips, latent demand or complete reported coverage. An absent grouped cell means zero records in this captured query scope. Metadata equality supports snapshot consistency but cannot prove underlying source accuracy or historical reporting availability.
