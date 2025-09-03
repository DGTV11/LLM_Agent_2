1. [x] Add file upload using ConceptCycle's impl (upload to Archival memory)

2. [x] Switch from sqlite to postgres
- optional_function_sets - json array as TEXT to TEXT[]
- tasks - json array as TEXT to TEXT[]
- recall storage+fifo queue - json obj as TEXT to JSONB
- all timestamps - DATETIME to TIMESTAMP

3. [x] migrate to orjson

4. [ ] test

5. [ ] make websocket single connection per session to reduce chance for errors

6. [ ] Find a way to be able to set env variables in docker compose file
