import copy


class ObjectResultHistory:
    def __init__(self):
        self.object_id = 0
        self.source_id = None
        self.frame_id = None
        self.class_id = None
        self.time_lost = None
        self.time_stamp = None
        self.time_detected = None
        self.last_update = False
        self.last_image = None
        self.lost_frames = 0
        self.track = None
        self.properties = dict()  # some object features in scene (i.e. is_moving, is_immovable, immovable_time, zone_visited, zone_time_spent etc)
        self.object_data = dict()  # internal object data

    def __deepcopy__(self, memodict={}):
        copy_instance = ObjectResultHistory()
        copy_instance.object_id = copy.deepcopy(self.object_id, memodict)
        copy_instance.source_id = copy.deepcopy(self.source_id, memodict)
        copy_instance.frame_id = copy.deepcopy(self.frame_id, memodict)
        copy_instance.class_id = copy.deepcopy(self.class_id, memodict)
        copy_instance.time_lost = copy.deepcopy(self.time_lost, memodict)
        copy_instance.time_stamp = copy.deepcopy(self.time_stamp, memodict)
        copy_instance.time_detected = copy.deepcopy(self.time_detected, memodict)
        copy_instance.last_update = copy.deepcopy(self.last_update, memodict)
        copy_instance.last_image = self.last_image
        copy_instance.lost_frames = copy.deepcopy(self.lost_frames,memodict)
        copy_instance.track = copy.deepcopy(self.track, memodict)
        return copy_instance


class ObjectResult(ObjectResultHistory):
    def __init__(self):
        super().__init__()
        self.history: list[ObjectResultHistory] = []

    def __str__(self):
        return f'ID: {self.object_id}, Source: {self.source_id}, Updated: {self.last_update}, Lost: {self.lost_frames}'

    def __deepcopy__(self, memodict={}):
        copy_instance = ObjectResult()
        copy_instance.object_id = copy.deepcopy(self.object_id, memodict)
        copy_instance.source_id = copy.deepcopy(self.source_id, memodict)
        copy_instance.frame_id = copy.deepcopy(self.frame_id, memodict)
        copy_instance.class_id = copy.deepcopy(self.class_id, memodict)
        copy_instance.time_lost = copy.deepcopy(self.time_lost, memodict)
        copy_instance.time_stamp = copy.deepcopy(self.time_stamp, memodict)
        copy_instance.time_detected = copy.deepcopy(self.time_detected, memodict)
        copy_instance.last_update = copy.deepcopy(self.last_update, memodict)
        copy_instance.last_image = self.last_image
        copy_instance.lost_frames = copy.deepcopy(self.lost_frames,memodict)
        copy_instance.track = copy.deepcopy(self.track, memodict)
        copy_instance.history = copy.deepcopy(self.history)
        return copy_instance

    def get_current_history_element(self):
        result = ObjectResultHistory()
        result.object_id = self.object_id
        result.source_id = self.source_id
        result.frame_id = self.frame_id
        result.class_id = self.class_id
        result.time_lost = self.time_lost
        result.time_stamp = self.time_stamp
        result.time_detected = self.time_detected
        result.last_update = self.last_update
        result.last_image = self.last_image
        result.lost_frames = self.lost_frames
        result.track = self.track
        result.properties = self.properties
        result.object_data = self.object_data
        return result


class ObjectResultList:
    def __init__(self):
        self.objects: list[ObjectResult] = []

    def find_last_frame_id(self):
        frame_id = 0
        for obj in self.objects:
            if frame_id < obj.frame_id:
                frame_id = obj.frame_id

        return frame_id

    def find_objects_by_frame_id(self, frame_id, use_history: bool):
        objs = []
        if frame_id is None:
            return self.objects

        for obj in self.objects:
            if frame_id == obj.frame_id:
                objs.append(obj)
            elif obj.history and use_history:
                for hist in obj.history:
                    if hist.frame_id == frame_id:
                        objs.append(obj)
                        break

        return objs

    def get_num_objects(self):
        return len(self.objects)
