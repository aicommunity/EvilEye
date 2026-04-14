from abc import ABC, abstractmethod
from queue import Queue, Empty
import threading
from ..core.base_class import EvilEyeBase
from ..core.frame import Frame
from ..core.ipc_contracts import attach_frame_contract


class PreprocessingBase(EvilEyeBase):
    ResultType = Frame
    def __init__(self):
        super().__init__()

        self.run_flag = False
        self.queue_in = Queue(maxsize=2)
        self.queue_out = Queue(maxsize=4)
        self.source_ids = []
        self.processing_thread = threading.Thread(target=self._process_impl)
        self.accepts_frame_handle = True
        self.emits_dto_type = "Frame"
        self.requires_materialized_frame = False

    def set_params_impl(self):
        self.source_ids = self.params.get('source_ids', [])

    def get_params_impl(self):
        params = dict()
        params['source_ids'] = self.source_ids
        return params

    def put(self, det_info):
        try:
            if self.queue_in.full():
                try:
                    old_info = self.queue_in.get_nowait()
                    self.logger.info(
                        "Preprocessing queue is full. Remove oldest item: source=%s frame=%s",
                        getattr(old_info, "source_id", None),
                        getattr(old_info, "frame_id", None),
                    )
                except Exception:
                    pass
            self.queue_in.put_nowait(det_info)
            return True
        except Exception:
            return False

    def get(self):
        if self.queue_out.empty():
            return None
        return self.queue_out.get_nowait()

    def get_queue_out_size(self):
        return self.queue_out.qsize()

    def get_source_ids(self):
        return self.source_ids

    def start(self):
        self.run_flag = True
        self.processing_thread.start()

    def stop(self):
        self.run_flag = False
        try:
            self.queue_in.put_nowait(None)
        except Exception:
            pass
        if self.processing_thread.is_alive():
            self.processing_thread.join()
        self.logger.info('Preprocessing stopped')

    def _materialize_frame_if_needed(self, frame):
        """Best-effort conversion of FrameHandle -> image for descriptor mode."""
        if frame is None:
            return frame
        if getattr(frame, "image", None) is not None:
            return frame
        handle = getattr(frame, "frame_handle", None)
        if handle is None:
            handle = getattr(frame, "frame_ref", None)
        if handle is None:
            return frame
        try:
            from ..core.frame_transport import SharedFrameTransport
            transport = SharedFrameTransport()
            frame.image = transport.get_frame_view(handle)
            try:
                transport.release_frame(handle)
            except Exception:
                pass
            try:
                setattr(frame, "frame_handle", None)
                setattr(frame, "frame_ref", None)
            except Exception:
                pass
        except Exception:
            # Keep standard behavior when descriptor materialization is unavailable.
            return frame
        return frame

    def _process_impl(self):
        while self.run_flag:
            try:
                item = self.queue_in.get(timeout=0.2)
            except Empty:
                continue
            if item is None:
                continue
            payload = item
            frame = item
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                payload, frame = item[0], item[1]
            frame = self._materialize_frame_if_needed(frame)
            preprocessed_frame = self._process_image(frame)
            preprocessed_frame = attach_frame_contract(preprocessed_frame, payload_version=1)
            if isinstance(item, tuple) and len(item) >= 2:
                result = (payload, preprocessed_frame)
            elif isinstance(item, list) and len(item) >= 2:
                result = [payload, preprocessed_frame]
            else:
                result = preprocessed_frame
            try:
                self.queue_out.put_nowait(result)
            except Exception:
                try:
                    _ = self.queue_out.get_nowait()
                except Exception:
                    pass
                try:
                    self.queue_out.put_nowait(result)
                except Exception:
                    pass

    @abstractmethod
    def _process_image(self, image):
        pass
