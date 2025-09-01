from abc import ABC, abstractmethod
from datetime import datetime

from .video_thread import VideoThread
from ..core.base_class import EvilEyeBase
import copy
from ..capture.video_capture_base import CaptureImage
from ..objects_handler.objects_handler import ObjectResultList
from timeit import default_timer as timer
from pympler import asizeof


class Visualizer(EvilEyeBase):
    def __init__(self, pyqt_slots: dict, pyqt_signals: dict):
        super().__init__()
        self.pyqt_slots = pyqt_slots
        self.pyqt_signals = pyqt_signals
        self.visual_threads: list[VideoThread] = []
        self.source_ids = []
        self.source_id_name_table = dict()
        self.source_video_duration = dict()
        self.fps = []
        self.font_params = []
        self.num_height = 1
        self.num_width = 1
        self.show_debug_info = False
        self.processing_frames: dict[int, list[CaptureImage]] = {}
        self.objects: list[ObjectResultList] = []
        self.last_displayed_frame = dict()
        self.visual_buffer_num_frames = 50
        self.text_config = {}  # Text configuration for rendering
        self.memory_consumption_detail = dict()


    def default(self):
        pass

    def init_impl(self):
        if len(self.visual_threads) > 0:
            self.visual_threads = []
        for i in range(len(self.source_ids)):
            self.visual_threads.append(VideoThread(self.source_ids[i], self.fps[i], self.num_height,
                                                           self.num_width, self.show_debug_info,
                                                   self.font_params[i] if self.font_params is not None else None,
                                                   text_config=self.text_config))
            self.visual_threads[-1].update_image_signal.connect(
                self.pyqt_slots['update_image'])  # Сигнал из потока для обновления label на новое изображение
            self.visual_threads[-1].add_zone_signal.connect(self.pyqt_slots['open_zone_win'])
            self.pyqt_signals['display_zones_signal'].connect(self.visual_threads[-1].display_zones_signal)
            self.pyqt_signals['add_zone_signal'].connect(self.visual_threads[-1].add_zone_clicked)

    def release_impl(self):
        for thr in self.visual_threads:
            thr.stop_thread()
        self.visual_threads = []

    def connect_to_signal(self, pyqt_signal):
        for i in range(len(self.source_ids)):  # Сигнал из потока для обновления label на новое изображение
            pyqt_signal.connect(self.visual_threads[i].display_zones_signal)

    def reset_impl(self):
        pass

    def set_params_impl(self):
        self.source_ids = self.params.get('source_ids', self.source_ids)
        self.show_debug_info = self.params.get('show_debug_info', False)
        self.fps = self.params.get('fps', self.fps)
        self.font_params = self.params.get('font_params', None)
        self.num_height = self.params.get('num_height', self.num_height)
        self.num_width = self.params.get('num_width', self.num_width)
        self.visual_buffer_num_frames = self.params.get('visual_buffer_num_frames', 50)
        self.text_config = self.params.get('text_config', {})

    def get_params_impl(self):
        params = dict()
        params['source_ids'] = self.source_ids
        params['show_debug_info'] = self.show_debug_info
        params['fps'] = self.fps
        params['font_params'] = self.font_params
        params['num_height'] = self.num_height
        params['num_width'] = self.num_width
        params['visual_buffer_num_frames'] = self.visual_buffer_num_frames
        params['text_config'] = self.text_config
        return params

    def start(self):
        for thr in self.visual_threads:
            thr.start_thread()

    def stop(self):
        for thr in self.visual_threads:
            thr.stop_thread()
        self.processing_frames = {}
        self.objects = None

    def set_current_main_widget_size(self, width, height):
        for j in range(len(self.visual_threads)):
            self.visual_threads[j].set_main_widget_size(width, height)

    def calc_memory_consumption(self):
        super().calc_memory_consumption()
        self.memory_consumption_detail['processing_frames'] = asizeof.asizeof(self.processing_frames)
        self.memory_consumption_detail['objects'] = asizeof.asizeof(self.objects)
        self.memory_consumption_detail['visual_threads'] = list()
        for thr in self.visual_threads:
            self.memory_consumption_detail['visual_threads'].append(asizeof.asizeof(thr))

    def get_debug_info(self, debug_info: dict | None):
        super().get_debug_info(debug_info)
        debug_info['memory_consumption_detail'] = self.memory_consumption_detail

    def update(self, processing_frames: list[CaptureImage], source_last_processed_frame_id: dict,
               objects: list[ObjectResultList], dropped_frames: list,  debug_info: dict):
        start_update = timer()
        remove_processed_idx = dict()
        for frame in processing_frames:
            if not frame.source_id in self.processing_frames.keys():
                self.processing_frames[frame.source_id] = []
            self.processing_frames[frame.source_id].append(frame)

            exceed_frames_num = len(self.processing_frames[frame.source_id]) - self.visual_buffer_num_frames
            if 0 < exceed_frames_num < len(self.processing_frames[frame.source_id]):
                del self.processing_frames[frame.source_id][exceed_frames_num:]

        self.objects = objects
        # Process visualization

        processed_sources = []

        for source_id, proc_frames in self.processing_frames.items():
            if source_id not in remove_processed_idx.keys():
                remove_processed_idx[source_id] = []

            #for i in range(len(proc_frames)):
            for i in reversed(range(len(proc_frames))):
                start_proc_frame = timer()
                frame = proc_frames[i]

                if self.last_displayed_frame.get(source_id, 0) >= frame.frame_id:
                    remove_processed_idx[source_id].append(i)
                    continue

                if source_id in processed_sources:
                    continue

    #            for data in dropped_frames:
    #                if source_id == data[0] and frame.frame_id == data[1]:
    #                    remove_processed_idx[source_id].append(i)
    #                    break

    #            if frame.frame_id > source_last_processed_frame_id[source_id]:
    #                continue

                start_find_objects = timer()
                source_index = self.source_ids.index(source_id)
                #objs = objects[source_index].objects
                objs = objects[source_index].find_objects_by_frame_id(frame.frame_id, use_history=False)

                #print(f"source={source_id} num_objs={len(objs)}")
                # print(f"Found {len(objs)} objects for visualization for source_id={frame.source_id} frame_id={frame.frame_id}")

                if len(objs) == 0 and objects[source_index].get_num_objects() > 0:
                    # remove_processed_idx[source_id].append(i)
                    continue

                start_append_data = timer()
                for j in range(len(self.visual_threads)):
                    if self.visual_threads[j].source_id == source_id:
                        data = (frame, objs, self.source_id_name_table[source_id],
                                self.source_video_duration.get(source_id, None), debug_info)
                        self.visual_threads[j].append_data(data)
                        self.last_displayed_frame[source_id] = frame.frame_id
                        processed_sources.append(source_id)
                        remove_processed_idx[source_id].append(i)
                        break
                end_proc_frame = timer()
                # print(f"Time frame: proc_frame[{end_proc_frame - start_proc_frame}], find_objects[{start_append_data - start_find_objects}, append[{end_proc_frame - start_find_objects}] secs")

            start_remove = timer()
            remove_processed_idx[source_id].sort(reverse=True)
            for index in remove_processed_idx[source_id]:
                del proc_frames[index]

            end_update = timer()
            # print(f"Time: update=[{end_update-start_update}] secs")

            #print(f"{datetime.now()}: Visual Queue size: {len(self.processing_frames)}. Processed sources: {processed_sources}")
