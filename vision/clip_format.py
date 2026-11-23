"""Layout of a recorded clip folder (FrameGrabber record mode and clip playback, C.5).

A clip folder holds the video and the laptop arrival time of every frame, so a test can
play the frames back with the same gaps as when they were recorded.
"""

VIDEO_FILE_NAME = "video.avi"
VIDEO_FOURCC = "MJPG"  # available in every OpenCV build, on Windows and Linux
ARRIVAL_TIMES_FILE_NAME = "arrival_times.csv"
FRAME_INDEX_COLUMN = "frame_index"
ARRIVAL_TIME_COLUMN = "t_arrival_s"
