"""Stage-1 audit fixes: crops-only IPC, SHM segment pool, pending reporter."""

from __future__ import annotations

import numpy as np

from evileye.attributes_detection.attribute_classifier import AttributeClassifier
from evileye.core.frame import Frame
from evileye.core.frame_transport import SharedFrameTransport
from evileye.object_tracker.tracking_results import TrackingResultList


def _make_tracking_with_roi(roi_data):
    tracking = TrackingResultList()
    tracking.roi_data = roi_data
    return tracking


def _make_frame(image):
    frame = Frame()
    frame.source_id = 0
    frame.frame_id = 7
    frame.time_stamp = 1.0
    frame.image = image
    return frame


class TestCropsOnlyIpc:
    def test_pack_process_item_ships_crops_not_frame(self):
        image = np.zeros((480, 640, 3), dtype=np.uint8)
        tracking = _make_tracking_with_roi(
            [{"track_id": 1, "roi_bbox": (10, 10, 60, 60)}]
        )
        packed = AttributeClassifier.pack_process_item((tracking, _make_frame(image)))

        assert packed is not None
        assert packed["marker"] == AttributeClassifier._PACKED_MARKER
        assert len(packed["crops"]) == 1
        assert packed["crops"][0]["track_id"] == 1
        crop = packed["crops"][0]["crop"]
        assert crop.shape == (50, 50, 3)
        # The payload must not carry the full frame pixels.
        assert "frame" not in packed
        assert crop.nbytes < image.nbytes

    def test_pack_process_item_skips_invalid_rois(self):
        image = np.zeros((480, 640, 3), dtype=np.uint8)
        tracking = _make_tracking_with_roi(
            [
                {"track_id": 1, "roi_bbox": None},
                {"track_id": None, "roi_bbox": (0, 0, 10, 10)},
            ]
        )
        packed = AttributeClassifier.pack_process_item((tracking, _make_frame(image)))
        assert packed is not None
        assert packed["crops"] == []

    def test_process_item_accepts_packed_payload(self, monkeypatch):
        module = AttributeClassifier()
        image = np.zeros((480, 640, 3), dtype=np.uint8)
        tracking = _make_tracking_with_roi(
            [{"track_id": 1, "roi_bbox": (10, 10, 60, 60)}]
        )
        crop = image[10:60, 10:60].copy()
        packed = {
            "marker": AttributeClassifier._PACKED_MARKER,
            "tracking_data": tracking,
            "crops": [{"track_id": 1, "crop": crop}],
        }
        captured = {}

        def fake_classify(self, roi):
            captured["roi"] = roi
            return {"hardhat": {"detected_now": True, "confidence": 0.9}}

        monkeypatch.setattr(AttributeClassifier, "_classify_roi_with_detector", fake_classify)
        result = module.process_item(packed, module)
        assert result is tracking
        assert tracking.attr_results[1]["hardhat"]["detected_now"] is True
        assert captured["roi"] is crop

    def test_restore_process_result_reattaches_local_frame(self):
        image = np.zeros((480, 640, 3), dtype=np.uint8)
        frame = _make_frame(image)
        tracking = _make_tracking_with_roi([])
        restored = AttributeClassifier.restore_process_result(tracking, (tracking, frame))
        assert restored == (tracking, frame)
        assert restored[1] is frame

    def test_restore_process_result_keeps_list_shape(self):
        image = np.zeros((480, 640, 3), dtype=np.uint8)
        frame = _make_frame(image)
        tracking = _make_tracking_with_roi([])
        restored = AttributeClassifier.restore_process_result(tracking, [tracking, frame])
        assert isinstance(restored, list)
        assert restored[1] is frame


class TestShmSegmentPool:
    def test_pool_reuses_segment_names(self):
        transport = SharedFrameTransport(pool_segments=True, pool_max_free=2)
        image = np.zeros((120, 160, 3), dtype=np.uint8)
        names = []
        for i in range(4):
            handle = transport.alloc_frame(image, frame_id=i, timestamp=float(i))
            names.append(handle.shm_name)
            transport.release_frame(handle)
        # With a pool of 2 free slots and identical shapes, names must repeat.
        assert names[1] == names[0]
        assert names[2] == names[0]
        transport.release_all_owned()

    def test_pool_respects_max_free(self):
        transport = SharedFrameTransport(pool_segments=True, pool_max_free=1)
        image = np.zeros((60, 80, 3), dtype=np.uint8)
        handles = [transport.alloc_frame(image, i, float(i)) for i in range(3)]
        for handle in handles:
            transport.release_frame(handle)
        # Only one idle segment kept; distinct names for the overflow.
        assert len({h.shm_name for h in handles}) >= 2
        transport.release_all_owned()

    def test_pool_without_pooling_behaves_like_before(self):
        transport = SharedFrameTransport(pool_segments=False)
        image = np.zeros((60, 80, 3), dtype=np.uint8)
        names = []
        for i in range(2):
            handle = transport.alloc_frame(image, i, float(i))
            names.append(handle.shm_name)
            transport.release_frame(handle)
        assert names[1] != names[0]
        transport.release_all_owned()

    def test_pooled_roundtrip_returns_pixels(self):
        transport = SharedFrameTransport(pool_segments=True, pool_max_free=1)
        image1 = np.full((60, 80, 3), 7, dtype=np.uint8)
        handle1 = transport.alloc_frame(image1, 1, 1.0)
        view1 = transport.get_frame_view(handle1)
        assert int(view1[0, 0, 0]) == 7
        transport.release_frame(handle1)
        # Reuse the pooled segment with different pixels.
        image2 = np.full((60, 80, 3), 9, dtype=np.uint8)
        handle2 = transport.alloc_frame(image2, 2, 2.0)
        assert handle2.shm_name == handle1.shm_name
        view2 = transport.get_frame_view(handle2)
        assert int(view2[0, 0, 0]) == 9
        transport.release_frame(handle2)
        transport.release_all_owned()


class TestAdapterPendingReporter:
    def test_pending_reporter_counts_in_flight_items(self):
        from evileye.core.plugin_runtime.item import ItemModuleAdapter
        from evileye.core.plugins import (
            PLUGIN_API_VERSION,
            ModuleSpec,
            PluginSpec,
            plugin_registry,
        )

        class _Echo:
            def process_item(self, item, state):
                return item

        plugin_id = "test.stage1-pending-probe"
        spec = ModuleSpec(
            "m", "processor_item", _Echo, execution_modes=("thread",)
        )
        plugin_registry.register_plugin(
            PluginSpec(plugin_id, PLUGIN_API_VERSION, modules=(spec,))
        )
        registered = plugin_registry.get_module(f"{plugin_id}/m")
        assert registered is not None
        adapter = ItemModuleAdapter(registered)
        adapter.execution_mode = "thread"
        adapter.set_params(
            module_id=f"{plugin_id}/m",
            execution_mode="thread",
            queue_size=8,
        )
        adapter._track_submitted_item()
        adapter._track_submitted_item()
        assert adapter.mp_pending_depth() == 2
        assert adapter.mp_diag_put_dropped() == 0
        assert adapter.mp_diag_pending_evict() == 0
        adapter._track_completed_item()
        assert adapter.mp_pending_depth() == 1

    def test_push_drained_output_drops_oldest_when_full(self):
        from evileye.core.plugin_runtime import item as item_module

        class _Probe:
            _drained_outputs = None  # set below

        import queue as queue_module

        probe = _Probe()
        probe._drained_outputs = queue_module.Queue(maxsize=2)
        item_module.ItemModuleAdapter._push_drained_output(probe, "a")
        item_module.ItemModuleAdapter._push_drained_output(probe, "b")
        item_module.ItemModuleAdapter._push_drained_output(probe, "c")
        assert probe._drained_outputs.get_nowait() == "b"
        assert probe._drained_outputs.get_nowait() == "c"
