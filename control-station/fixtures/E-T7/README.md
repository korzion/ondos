# E-T7 Recording

Requirement: E-R5

**Method:** Run two test games with new game_ids; close the app during the second.

**Pass if:** Two files, each starting with the maze data; the second keeps growing.

## Inputs

`input.jsonl` describes two games and their retained maze and distance-map data. While `input.jsonl` plays, the test keeps a `cs_app` connection open in place of the Control Station app; it then closes that connection (`sys/online/cs_app` = false) and plays `after_app_close.jsonl`, whose live ball samples must appear in the second file. The game IDs and message values can be edited, but each message must remain valid for its topic schema.

The test checks that exactly one file is created per game, each starting with a valid IF-09 header followed by the maze data, and that the ball samples of `after_app_close.jsonl` appear in the second file after the app has disconnected.

The test starts `node_modules/tsx/dist/cli.mjs` directly, so run `npm install` at the repo root first.
