"""Utilities for resolving configured labels to model class IDs."""

from collections.abc import Mapping, Sequence
from typing import Any


def resolve_model_class_mapping(
    requested_names: Sequence[str],
    model_names: Any,
    *,
    module_name: str,
) -> dict[str, int]:
    """Resolve requested labels from a model's ``names`` metadata.

    Model class IDs are not necessarily contiguous or ordered like a module's
    configured labels. Missing labels must be mapped explicitly by the user.
    """
    labels = list(requested_names)
    if not labels:
        return {}

    if isinstance(model_names, Mapping):
        entries = model_names.items()
    elif isinstance(model_names, Sequence) and not isinstance(model_names, (str, bytes)):
        entries = enumerate(model_names)
    else:
        entries = ()

    ids_by_name = {str(name): int(class_id) for class_id, name in entries}
    missing = [name for name in labels if name not in ids_by_name]
    if missing:
        reason = (
            "checkpoint does not expose class names"
            if not ids_by_name
            else f"checkpoint has no classes {missing!r}"
        )
        raise ValueError(
            f"{module_name} cannot resolve model classes: {reason}; "
            "configure class_mapping explicitly"
        )
    return {name: ids_by_name[name] for name in labels}
