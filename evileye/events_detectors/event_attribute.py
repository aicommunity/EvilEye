from .event import Event
import copy


class AttributeEvent(Event):
    def __init__(self, timestamp, alarm_type, source_id, object_id, matched_event_name, matched_attrs: list[str], is_finished=False, obj=None):
        super().__init__(timestamp, alarm_type, is_finished)
        self.source_id = source_id
        self.object_id = object_id
        self.matched_event_name = matched_event_name
        self.matched_attrs = list(matched_attrs)
        self.long_term = True
        self.time_found = None
        self.time_finished = timestamp if is_finished else None
        # Images and boxes for debug saving
        self.img_found = None
        self.img_finished = None
        self.box_found = None
        self.box_finished = None
        self.class_id = None
        # Video paths
        self.video_path_found = None
        self.video_path_finished = None

        if obj is not None:
            if not is_finished:
                # Use .copy() for numpy arrays in CaptureImage instead of deepcopy
                if obj.last_image and hasattr(obj.last_image, 'image') and obj.last_image.image is not None:
                    # Create shallow copy of CaptureImage and copy only numpy array
                    import copy as cp
                    self.img_found = cp.copy(obj.last_image)
                    if hasattr(self.img_found, 'image'):
                        self.img_found.image = obj.last_image.image.copy()
                else:
                    self.img_found = obj.last_image
                self.box_found = obj.track.bounding_box if hasattr(obj, 'track') else None
                self.time_found = timestamp
                self.class_id = getattr(obj, 'class_id', None)
            else:
                # Use .copy() for numpy arrays in CaptureImage instead of deepcopy
                if obj.last_image and hasattr(obj.last_image, 'image') and obj.last_image.image is not None:
                    import copy as cp
                    self.img_finished = cp.copy(obj.last_image)
                    if hasattr(self.img_finished, 'image'):
                        self.img_finished.image = obj.last_image.image.copy()
                else:
                    self.img_finished = obj.last_image
                self.box_finished = obj.track.bounding_box if hasattr(obj, 'track') else None
                self.class_id = getattr(obj, 'class_id', None)

    def __str__(self):
        return f'Id: {self.event_id}, Source: {self.source_id}, Obj_id: {self.object_id}, Event: {self.matched_event_name}, Attrs: {self.matched_attrs}'

    def __eq__(self, other):
        return self.source_id == other.source_id and self.object_id == other.object_id and self.matched_event_name == other.matched_event_name

    def update_on_finished(self, finished_event):
        self.time_finished = finished_event.timestamp
        self.img_finished = finished_event.img_finished
        self.box_finished = finished_event.box_finished
        self.video_path_finished = getattr(finished_event, 'video_path_finished', None)

    def get_time_finished(self):
        return self.time_finished


