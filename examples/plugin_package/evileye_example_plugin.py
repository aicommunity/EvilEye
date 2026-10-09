"""Small reference plugin for EvilEye's public entry-point API."""

from evileye.core.plugins import ModuleSpec, PLUGIN_API_VERSION, PluginSpec


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
            ),
        ),
    )
