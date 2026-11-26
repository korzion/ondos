# E-T8 No replay in the recording

Requirement: E-R5

**Method:** Replay a game during a live test game.

**Pass if:** No replay message in the file; live messages are still recorded.

## Inputs

`input.jsonl` starts a game. `live.jsonl` publishes a live platform sample before and after `replay.jsonl` is played through the shared replay tool. `replay.jsonl` contains two recorded Vision ball samples. The game ID and message values can be edited, but each message must remain valid for its topic schema.

The test checks that the shared replay tool played the Vision samples of `replay.jsonl` during the live game, that none of them (neither a `writer = replay` row nor a ball sample at their coordinates) is in the recording, and that both live platform samples are.

The test starts `node_modules/tsx/dist/cli.mjs` directly, so run `npm install` at the repo root first.
