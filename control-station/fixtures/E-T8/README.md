# E-T8 No replay in the recording

Requirement: E-R5

**Method:** Replay a game during a live test game.

**Pass if:** The shared replay tool plays the recorded Vision samples during the live game; no replay message appears in the recording, and live platform messages remain recorded.

## Inputs

`input.jsonl` starts a game. `live.jsonl` publishes a live platform sample before and after `replay.jsonl` is played through the shared replay tool. `replay.jsonl` contains two recorded Vision ball samples. The game ID and message values can be edited, but each message must remain valid for its topic schema.
