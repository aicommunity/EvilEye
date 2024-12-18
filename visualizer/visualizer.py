from abc import ABC, abstractmethod
from datetime import datetime

from visualizer.video_thread import VideoThread
import core
import copy
from capture.video_capture_base import CaptureImage
from objects_handler.objects_handler import ObjectResultList
from timeit import default_timer as timer

class Visualizer(core.EvilEyeBase):
    def __init__(self, pyqt_slot):
        super().__init__()
        self.qt_slot = pyqt_slot
        self.visual_threads: list[VideoThread] = []
        self.source_ids = []
        self.source_id_name_table = dict()
        self.source_video_duration = dict()
        self.fps = []
        self.num_height = 1
        self.num_width = 1
        self.show_debug_info = False
        self.processing_frames: list[CaptureImage] = []
        self.objects: list[ObjectResultList] = []
        self.last_displayed_frame = dict()
        self.visual_buffer_num_frames = 10

    def default(self):
        pass

    def init_impl(self):
        if len(self.visual_threads) > 0:
            self.visual_threads = []
        for i in range(len(self.source_ids)):
            self.visual_threads.append(VideoThread(self.source_ids[i], self.fps[i], self.num_height,
                                                           self.num_width, self.show_debug_info))
            self.visual_threads[-1].update_image_signal.connect(
                        self.qt_slot)  # Сигнал из потока для обновления label на новое изображение

    def release_impl(self):
        for thr in self.video_threads:
            thr.stop_thread()
        self.video_threads = []

    def reset_impl(self):
        pass

    def set_params_impl(self):
        self.source_ids = self.params['source_ids']
        self.show_debug_info = self.params.get('show_debug_info', False)
        self.fps = self.params['fps']
        self.num_height = self.params['num_height']
        self.num_width = self.params['num_width']
        self.visual_buffer_num_frames = self.params.get('visual_buffer_num_frames', 10)

    def start(self):
        for thr in self.visual_threads:
            thr.start_thread()

    def stop(self):
        for thr in self.visual_threads:
            thr.stop_thread()
        self.processing_frames = []
        self.objects = None

    def set_current_main_widget_size(self, width, height):
        for j in range(len(self.visual_threads)):
            self.visual_threads[j].set_main_widget_size(width, height)

    def update(self, processing_frames: list[CaptureImage], source_last_processed_frame_id: dict, objects: list[ObjectResultList], debug_info: dict):
        start_update = timer()
        self.processing_frames.extend(processing_frames)
        self.objects = objects
        # Process visualization
        remove_processed_idx = []

        processed_sources = []

        if len(self.processing_frames) < len(self.source_ids)*self.visual_buffer_num_frames:
            return

        for i in range(len(self.processing_frames)):
            start_proc_frame = timer()
            frame = self.processing_frames[i]
            source_id = frame.source_id
            if source_id in processed_sources:
                continue

            if self.last_displayed_frame.get(source_id, 0) >= frame.frame_id:
                remove_processed_idx.append(i)
                continue

            if frame.frame_id > source_last_processed_frame_id[frame.source_id]:
                continue

            start_find_objects = timer()
            source_index = self.source_ids.index(source_id)
            objs = objects[source_index].find_objects_by_frame_id(frame.frame_id, use_history=False)
#            objs = objects[source_id].find_objects_by_frame_id(None)
#            objs = objects[source_id].objects
#            print(f"Found {len(objs)} objects for visualization for source_id={frame.source_id} frame_id={frame.frame_id}")

            if len(objs) == 0 and objects[source_index].get_num_objects() > 0:
                #remove_processed_idx.append(i)
                continue

            start_append_data = timer()
            for j in range(len(self.visual_threads)):
                if self.visual_threads[j].source_id == source_id:
                    data = (frame, objs, self.source_id_name_table[frame.source_id], self.source_video_duration.get(frame.source_id, None), debug_info)
                    self.visual_threads[j].append_data(copy.deepcopy(data))
                    self.last_displayed_frame[source_id] = frame.frame_id
                    processed_sources.append(source_id)
                    break
            remove_processed_idx.append(i)
            end_proc_frame = timer()
            # print(f"Time frame: proc_frame[{end_proc_frame - start_proc_frame}], find_objects[{start_append_data - start_find_objects}, append[{end_proc_frame - start_find_objects}] secs")

        start_remove = timer()
        remove_processed_idx.sort(reverse=True)
        for index in remove_processed_idx:
            del self.processing_frames[index]

        end_update = timer()
        # print(f"Time: update=[{end_update-start_update}] secs")

        # print(f"{datetime.now()}: Visual Queue size: {len(self.processing_frames)}. Processed sources: {processed_sources}")
