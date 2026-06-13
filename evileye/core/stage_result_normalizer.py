"""Normalize (data, frame) pipeline tuples for downstream stages.

See also: [thread_vs_mp_contracts.md](../docs/thread_vs_mp_contracts.md) §8.2 (post-drain only).
ProcessorStep must not drain MP outputs before all ``put`` calls in one ``process()`` pass.
"""


def normalize_result_meta(result):
    """Align source_id / frame_id / time_stamp on data from frame."""
    try:
        if not (isinstance(result, (list, tuple)) and len(result) >= 2):
            return result
        data = result[0]
        frame = result[1]
        if data is None or frame is None:
            return result
        if hasattr(data, "source_id") and hasattr(frame, "source_id"):
            data.source_id = frame.source_id
        if hasattr(data, "frame_id") and hasattr(frame, "frame_id"):
            data.frame_id = frame.frame_id
        if hasattr(data, "time_stamp") and hasattr(frame, "time_stamp"):
            data.time_stamp = frame.time_stamp
    except Exception:
        pass
    return result
