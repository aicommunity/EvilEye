
class Frame:
    def __init__(self):
        self.source_id = None
        self.frame_id = None
        self.current_video_frame = None
        self.current_video_position = None
        self.time_stamp = None
        self.image = None
        self.subscribers = []

CaptureImage = Frame