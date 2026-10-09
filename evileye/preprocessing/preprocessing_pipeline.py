import copy

import cv2
import numpy as np
from ..utils import utils
from . import PreprocessingBase, PreprocessingFactory
from ..core.base_class import EvilEyeBase


# from preprocessing.steps import Input, Normalize, Output, Inpaint, Clahe


@EvilEyeBase.register(
    "PreprocessingPipeline",
    kind="processor_item",
    execution_modes=("thread", "process"),
    capabilities=("accepts_frame_handle", "emits_dto_type:Frame"),
)
class PreprocessingPipeline(PreprocessingBase):
    def __init__(self):
        super().__init__()
        self.json_path = None
        self.preprocessSequence = None
        self.in_place_allowed = False
        self.copy_required = True

    def init_impl(self):
        self.json_path = self.json_path or 'configs/preprocessing_pipeline.json'
        factory = PreprocessingFactory(self.json_path)
        self.preprocessSequence = factory.build_pipeline()
        return True

    def create_state(self, config):
        """Initialize this legacy preprocessor inside the selected plugin worker."""
        self.set_params(**dict(config or {}))
        if not self.init():
            raise RuntimeError("PreprocessingPipeline failed to initialize")
        return self

    def process_item(self, item, state):
        """Preserve the old frame and (payload, frame) preprocessing contract."""
        processor = state or self
        is_pair = isinstance(item, (list, tuple)) and len(item) >= 2
        if is_pair:
            payload, frame = item[0], item[1]
            preserve_tuple = isinstance(item, tuple)
        else:
            payload, frame = None, item
            preserve_tuple = False

        frame = processor._materialize_frame_if_needed(frame)
        processed_frame = processor._process_image(frame)
        from ..core.ipc_contracts import attach_frame_contract

        processed_frame = attach_frame_contract(processed_frame, payload_version=1)
        if not is_pair:
            return processed_frame
        if preserve_tuple:
            return payload, processed_frame
        return [payload, processed_frame]

    def release_impl(self):
        pass

    def reset_impl(self):
        pass

    def set_params_impl(self):
        super().set_params_impl()
        self.json_path = self.params.get('pipeline_file_name', '')
        self.in_place_allowed = bool(self.params.get("in_place_allowed", False))
        self.copy_required = bool(self.params.get("copy_required", not self.in_place_allowed))

    def get_params_impl(self):
        params = super().get_params_impl()
        params['pipeline_file_name'] = self.json_path
        params["in_place_allowed"] = self.in_place_allowed
        params["copy_required"] = self.copy_required
        return params

    def default(self):
        self.params.clear()

    def _process_image(self, image):
        processed_image = image
        if self.copy_required and not self.in_place_allowed:
            processed_image = copy.copy(image)
            if image is not None and getattr(image, "image", None) is not None:
                processed_image.image = np.array(image.image, copy=True)

        if self.preprocessSequence is not None and getattr(processed_image, "image", None) is not None:
            processed_image.image = self.preprocessSequence.applySequence(processed_image.image)

        prev_version = int(getattr(image, "frame_version", 0) or 0)
        setattr(processed_image, "frame_version", prev_version + 1)
        return processed_image
