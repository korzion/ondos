// Main side of the recording files (#84): lists and reads the recordings for ReplayController.
// The renderer may only name a file inside the recording folder; anything else is refused.
import { ipcMain } from "electron";
import { readdir, readFile } from "node:fs/promises";
import { basename, join, resolve } from "node:path";
import { LIST_RECORDINGS_CHANNEL, READ_RECORDING_CHANNEL, RECORDING_FILE_EXTENSION } from "../common/recordingFiles";

// ASSUMPTION: the same default as the Recorder (IF-09: recordings/ in the folder it starts in,
// control-station/ with npm run). A recording_folder set in the cs variables is not followed yet:
// the Recorder applies it, but this process and the replay tool (--recordings) keep the default.
const RECORDING_FOLDER = "recordings";

function recording_folder_path(): string {
    return resolve(RECORDING_FOLDER);
}

function is_recording_file_name(name: unknown): name is string {
    return typeof name === "string"
        && name === basename(name)
        && !name.startsWith(".")
        && name.endsWith(RECORDING_FILE_EXTENSION);
}

function without_extension(name: string): string {
    return name.slice(0, -RECORDING_FILE_EXTENSION.length);
}

async function list_recordings(): Promise<string[]> {
    try {
        const entries = await readdir(recording_folder_path(), { withFileTypes: true });
        return entries
            .filter((entry) => entry.isFile() && is_recording_file_name(entry.name))
            .map((entry) => entry.name)
            // Names start with the game_id (YYYYMMDD-HHMMSS), so this is newest first. The extension is
            // left out of the comparison, so "<game_id>-2.jsonl" comes before "<game_id>.jsonl".
            .sort((a, b) => without_extension(b).localeCompare(without_extension(a)));
    } catch (error) {
        // No recording yet: the Recorder creates the folder with the first game.
        if ((error as NodeJS.ErrnoException).code === "ENOENT") return [];
        throw error;
    }
}

async function read_recording(name: unknown): Promise<string> {
    if (!is_recording_file_name(name)) {
        throw new Error(`not a recording file name: ${String(name)}`);
    }
    return readFile(join(recording_folder_path(), name), "utf8");
}

export function handle_recording_files(): void {
    ipcMain.handle(LIST_RECORDINGS_CHANNEL, () => list_recordings());
    ipcMain.handle(READ_RECORDING_CHANNEL, (_event, name: unknown) => read_recording(name));
}
