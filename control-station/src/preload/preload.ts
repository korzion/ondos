// Preload script: gives the sandboxed renderer the recording files (#84) and nothing else.
import { contextBridge, ipcRenderer } from "electron";
import {
    LIST_RECORDINGS_CHANNEL, READ_RECORDING_CHANNEL, RECORDING_FILES_API_NAME, type RecordingFilesApi,
} from "../common/recordingFiles";

const recording_files: RecordingFilesApi = {
    list: () => ipcRenderer.invoke(LIST_RECORDINGS_CHANNEL),
    read: (name: string) => ipcRenderer.invoke(READ_RECORDING_CHANNEL, name),
};

contextBridge.exposeInMainWorld(RECORDING_FILES_API_NAME, recording_files);
