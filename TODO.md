1. [x] Add file upload using ConceptCycle's impl (upload to Archival memory)

2. [ ] Switch from sqlite to postgres
- optional_function_sets - json array as TEXT to TEXT[]
- tasks - json array as TEXT to TEXT[]
- recall storage+fifo queue - json obj as TEXT to JSONB
- all timestamps - DATETIME to TIMESTAMP

3. [ ] migrate to orjson

4. [ ] Find a way to be able to set env variables in docker compose file
