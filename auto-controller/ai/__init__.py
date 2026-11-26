"""AI part of D · Auto Controller (D.5): AIController, the shared observation code and, later, Learning.

auto-controller/ is on sys.path (it holds run_test.py), so this package is imported as `ai`.
"""
from .recording_reader import (
    LoadedRecording,
    RecordingReader,
    RecordingStats,
    TrainingRow,
)

__all__ = [
    "LoadedRecording",
    "RecordingReader",
    "RecordingStats",
    "TrainingRow",
]
