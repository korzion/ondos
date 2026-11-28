// Recording files for ReplayController (#84): what the main process, the preload script and the
// renderer agree on. The renderer is sandboxed, so the main process lists and reads the files and
// the preload script passes the calls over IPC.

// IPC channels handled by the main process (src/main/recordingFiles.ts).
export const LIST_RECORDINGS_CHANNEL = "recordings:list";
export const READ_RECORDING_CHANNEL = "recordings:read";

// Name under which the preload script puts the API on the renderer's window object.
export const RECORDING_FILES_API_NAME = "recording_files";

// Recording files are <game_id>.jsonl (IF-09).
export const RECORDING_FILE_EXTENSION = ".jsonl";

export interface RecordingFilesApi {
    // File names in the recording folder, newest first.
    list(): Promise<string[]>;
    // Full text of one recording; name is a file name returned by list().
    read(name: string): Promise<string>;
}
