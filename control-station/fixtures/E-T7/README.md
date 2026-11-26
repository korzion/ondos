# E-T7 Recording

Requirement: E-R5

**Method:** Run two test games with new game_ids; close the app during the second.

**Pass if:** Exactly one file per game is created, each starting with a valid IF-09 header followed by the maze data; after the app disconnects during the second game, the live ball samples sent afterwards still appear in its file.

## Inputs

`input.jsonl` describes two games and their retained maze and distance-map data. While `input.jsonl` plays, the test keeps a `cs_app` connection open in place of the Control Station app; it then closes that connection (`sys/online/cs_app` = false) and plays `after_app_close.jsonl`, whose live ball samples must appear in the second file. The game IDs and message values can be edited, but each message must remain valid for its topic schema.
