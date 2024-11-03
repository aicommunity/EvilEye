from abc import ABC, abstractmethod
from datetime import datetime

from numpy.lib.utils import source

from visualizer.video_thread import VideoThread
import core
import copy
from capture.video_capture_base import CaptureImage
from objects_handler.objects_handler import ObjectResultList

class Visualizer(core.EvilEyeBase):
    def __init__(self, pyqt_slot):
        super().__init__()
        self.qt_slot = pyqt_slot
        self.visual_threads: list[VideoThread] = []
        self.source_ids = []
        self.fps = []
        self.num_height = 1
        self.num_width = 1
        self.processing_frames: list[CaptureImage] = []
        self.objects: list[ObjectResultList] = []
        self.last_displayed_frame = dict()

    def default(self):
        pass

    def init_impl(self):
        if len(self.visual_threads) > 0:
            self.visual_threads = []
        for i in range(len(self.source_ids)):
            self.visual_threads.append(VideoThread(self.source_ids[i], self.fps[i], self.num_height,
                                                           self.num_width))
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
        self.fps = self.params['fps']
        self.num_height = self.params['num_height']
        self.num_width = self.params['num_width']

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


    def update(self, processing_frames: list[CaptureImage], objects: list[ObjectResultList]):
        self.processing_frames.extend(processing_frames)
        self.objects = objects
        # Process visualization
        remove_processed_idx = []

        processed_sources = []

        if len(self.processing_frames) < len(self.source_ids)*5:
            return

        for i in range(len(self.processing_frames)):
            frame = self.processing_frames[i]
            source_id = frame.source_id
            if source_id in processed_sources:
                continue

            if source_id in self.last_displayed_frame.keys() and self.last_displayed_frame[source_id] >= frame.frame_id:
                remove_processed_idx.append(i)
                continue

            objs = objects[source_id].find_objects_by_frame_id(frame.frame_id)
            for j in range(len(self.visual_threads)):
                if self.visual_threads[j].source_id == source_id:
                    self.visual_threads[j].append_data((copy.deepcopy(frame), objs))
                    self.last_displayed_frame[source_id] = frame.frame_id
                    processed_sources.append(source_id)
                    break
            remove_processed_idx.append(i)


        remove_processed_idx.sort(reverse=True)
        for index in remove_processed_idx:
            del self.processing_frames[index]

        print(f"{datetime.now()}: Visual Queue size: {len(self.processing_frames)}. Processed sources: {processed_sources}")
