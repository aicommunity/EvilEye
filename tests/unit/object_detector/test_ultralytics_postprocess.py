from evileye.object_detector.ultralytics_postprocess import (
    apply_ultralytics_optimizations,
    build_class_mapping_from_names,
)


class _FakeModel:
    def __init__(self):
        self.fused = False
        self.halved = False
        self.names = {0: "person", 1: "car"}

    def fuse(self):
        self.fused = True

    def half(self):
        self.halved = True


def test_apply_ultralytics_optimizations_fuse_and_half():
    model = _FakeModel()
    apply_ultralytics_optimizations(model, half=True)
    assert model.fused is True
    assert model.halved is True


def test_apply_ultralytics_optimizations_skips_half_when_disabled():
    model = _FakeModel()
    apply_ultralytics_optimizations(model, half=False)
    assert model.fused is True
    assert model.halved is False


def test_build_class_mapping_from_names():
    mapping = build_class_mapping_from_names({0: "person", 1: "car"})
    assert mapping == {"person": 0, "car": 1}
