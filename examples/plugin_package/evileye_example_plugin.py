"""Reference modules and a user-defined pipeline for the public entry-point API."""

from evileye.core.pipeline_base import PipelineBase
from evileye.core.plugins import (
    ModuleSpec,
    PipelineSpec,
    PLUGIN_API_VERSION,
    PluginSpec,
)


class AddLabel:
    def __init__(self, config=None):
        self.label = (config or {}).get("label", "example")

    def create_state(self, config):
        return {"processed": 0}

    def process_item(self, item, state):
        state["processed"] += 1
        if isinstance(item, (list, tuple)) and len(item) == 2:
            data, frame = item
            if isinstance(data, dict):
                data = dict(data)
                data["plugin_label"] = self.label
            return [data, frame]
        if isinstance(item, dict):
            result = dict(item)
            result["plugin_label"] = self.label
            result["plugin_item_number"] = state["processed"]
            return result
        return {"value": item, "plugin_label": self.label}


class MarkerPipeline(PipelineBase):
    """Small IPipeline implementation proving an external pipeline lifecycle."""

    def __init__(self, default_marker="example"):
        super().__init__()
        self.marker = str(default_marker)
        self.sequence = 0
        self.running = False
        self._sources = []

    def set_params_impl(self):
        self.marker = str(self.params.get("marker", self.marker))

    def get_params_impl(self):
        return {"pipeline_class": self.__class__.__name__, "marker": self.marker}

    def start(self):
        self.running = True

    def stop(self):
        self.running = False

    def process(self):
        if not self.running:
            raise RuntimeError("MarkerPipeline must be started before process()")
        self.sequence += 1
        result = {"marker": self.marker, "sequence": self.sequence}
        self._current_results = result
        self.add_result(result)
        return result

    def get_sources(self):
        return list(self._sources)

    def generate_default_structure(self, num_sources: int):
        return {"marker": self.marker, "source_count": int(num_sources)}


def make_marker_pipeline(dependencies):
    # The factory receives PipelineDependencies from the public plugin SPI.
    marker = dependencies.config.raw_config.get("factory_marker", "example")
    return MarkerPipeline(default_marker=marker)


def load_plugin():
    return PluginSpec(
        plugin_id="example",
        api_version=PLUGIN_API_VERSION,
        modules=(
            ModuleSpec(
                module_id="add-label",
                kind="processor_item",
                factory=AddLabel,
                execution_modes=("thread", "process"),
                capabilities=("accepts_frame_handle",),
            ),
        ),
        pipelines=(
            PipelineSpec("marker-pipeline", make_marker_pipeline),
        ),
    )
