from __future__ import annotations

from typing import Optional

from ..core.base_class import EvilEyeBase
from ..core.frame import Frame
from . import PreprocessingBase, PreprocessingFactory


DEFAULT_PIPELINE_PATH = "configs/preprocessing_pipeline.json"


@EvilEyeBase.register("PreprocessingPipeline")
class PreprocessingPipeline(PreprocessingBase):
    """Препроцессинг кадров по конфигурации из JSON."""

    def __init__(self):
        super().__init__()
        self.json_path: str | None = DEFAULT_PIPELINE_PATH
        self.preprocessSequence = None

    def init_impl(self):
        pipeline_path = self.json_path or DEFAULT_PIPELINE_PATH
        factory = PreprocessingFactory(pipeline_path)
        self.preprocessSequence = factory.build_pipeline()
        return True

    def release_impl(self):
        pass

    def reset_impl(self):
        pass

    def set_params_impl(self):
        super().set_params_impl()
        self.json_path = self.params.get("pipeline_file_name", DEFAULT_PIPELINE_PATH)

    def get_params_impl(self):
        params = super().get_params_impl()
        params["pipeline_file_name"] = self.json_path
        return params

    def default(self):
        self.params.clear()
        self.json_path = DEFAULT_PIPELINE_PATH

    def _process_image(self, image: Frame) -> Optional[Frame]:
        if self.preprocessSequence is None:
            return image

        processed_frame = Frame()
        processed_frame.source_id = image.source_id
        processed_frame.frame_id = image.frame_id
        processed_frame.current_video_frame = image.current_video_frame
        processed_frame.current_video_position = image.current_video_position
        processed_frame.time_stamp = image.time_stamp
        processed_frame.subscribers = list(image.subscribers) if image.subscribers else []
        processed_frame.image = self.preprocessSequence.applySequence(image.image)
        return processed_frame
