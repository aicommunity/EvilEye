class Frame:
    """Mutable envelope for one source frame and its capture metadata.

    Built-in capture modules emit ``image`` as an HxWx3 BGR NumPy array.
    ``source_id`` identifies the logical input and ``frame_id`` identifies its
    sequence position. ``connection_generation`` starts at zero and advances
    when a source reconnects. A source that resets its frame sequence must also
    advance the generation so downstream stateful modules can reset.

    ``time_stamp`` is acquisition wall time in seconds. ``pts_ns`` and
    ``media_pts_sec`` are optional media-clock values. File position/duration
    fields are optional and are populated only by video-file sources. A runtime
    may additionally attach ``frame_handle`` when the image is transported via
    shared memory; ordinary source plugins should populate ``image`` directly.
    """

    def __init__(self):
        self.source_id = None
        self.frame_id = None
        self.connection_generation = 0
        self.current_video_frame = None
        self.current_video_position = None
        self.source_video_duration = None
        self.time_stamp = None
        self.pts_ns = None
        self.media_pts_sec = None
        self.image = None
        self.subscribers = []


CaptureImage = Frame
