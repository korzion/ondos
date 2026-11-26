# E-T7 Recording

Requirement: E-R5

**Method:** Run two test games with new game_ids; close the app during the second.

**Pass if:** Two files are created with a valid IF-09 header and maze data; after the app publisher disconnects during the second game, its file keeps growing from live messages.

## Inputs

`input.jsonl` describes two games and their retained maze and distance-map data. `after_app_close.jsonl` simulates the app disconnecting and then publishes more live ball samples. The game IDs and message values can be edited, but each message must remain valid for its topic schema.
