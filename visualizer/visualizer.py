from abc import ABC, abstractmethod

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

    def update(self, processing_frames: list[CaptureImage], objects: list[ObjectResultList]):
        self.processing_frames.extend(processing_frames)
        self.objects = objects
        # Process visualization
        remove_processed_idx = []
        for i in range(len(self.visual_threads)):
            source_id = self.visual_threads[i].source_id
            last_frame_id = None
            if len(self.objects) < source_id:
                last_frame_id = objects[source_id].find_last_frame_id()

            if last_frame_id:
                for j in range(len(self.processing_frames)):
                    if self.processing_frames[j].source_id == i:
                        if self.processing_frames[j].frame_id < last_frame_id:
                            remove_processed_idx.append(j)
                        if self.processing_frames[j].frame_id == last_frame_id:
                            self.visual_threads[i].append_data((copy.deepcopy(self.processing_frames[j]), objects[source_id]))
                            break
            else:
                for j in reversed(range(len(self.processing_frames))):
                    if self.processing_frames[j].source_id == i:
                        self.visual_threads[i].append_data((copy.deepcopy(self.processing_frames[j]), objects[source_id]))
                        break

        remove_processed_idx.sort(reverse=True)
        for index in remove_processed_idx:
            del self.processing_frames[index]

        if len(self.processing_frames) > 30:
            del self.processing_frames[(len(self.processing_frames) - 30):]