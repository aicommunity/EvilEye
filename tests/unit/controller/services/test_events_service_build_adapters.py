from unittest.mock import MagicMock

from evileye.controller.services.events_service import EventsService, JSON_EVENT_ADAPTER_CLASSES


class _DbConnected:
    def is_connected(self):
        return True


class _DbDisconnected:
    def is_connected(self):
        return False


def test_build_event_adapters_json_only_when_no_db(monkeypatch):
    started = []

    class _FakeJsonAdapter:
        def __init__(self, _ctrl):
            pass

        def set_params(self, **kwargs):
            return None

        def init(self):
            return None

        def start(self):
            started.append(self)

        def get_event_name(self):
            return "fake_json"

    fake_tuple = tuple(_FakeJsonAdapter for _ in JSON_EVENT_ADAPTER_CLASSES)
    monkeypatch.setattr(
        "evileye.controller.services.events_service.JSON_EVENT_ADAPTER_CLASSES",
        fake_tuple,
    )

    svc = EventsService()
    adapters = svc.build_event_adapters(
        params={"database": {"image_dir": "EvilEyeData"}},
        use_database=False,
        db_controller=None,
    )
    assert len(adapters) == len(JSON_EVENT_ADAPTER_CLASSES)
    assert len(started) == len(JSON_EVENT_ADAPTER_CLASSES)


def test_build_event_adapters_includes_db_when_connected():
    svc = EventsService()
    db_cam = MagicMock(get_event_name=lambda: "cam")
    db_fov = MagicMock(get_event_name=lambda: "fov")
    db_zone = MagicMock(get_event_name=lambda: "zone")

    adapters = svc.build_event_adapters(
        params={"database": {"image_dir": "EvilEyeData"}},
        use_database=True,
        db_controller=_DbConnected(),
        db_adapter_fov_events=db_fov,
        db_adapter_cam_events=db_cam,
        db_adapter_zone_events=db_zone,
    )
    assert db_fov in adapters
    assert db_cam in adapters
    assert db_zone in adapters


def test_build_event_adapters_skips_db_when_not_connected(monkeypatch):
    db_mock = MagicMock(get_event_name=lambda: "cam")

    class _MinimalJsonAdapter:
        def __init__(self, _ctrl):
            pass

        def set_params(self, **kwargs):
            pass

        def init(self):
            pass

        def start(self):
            pass

        def get_event_name(self):
            return "json"

    monkeypatch.setattr(
        "evileye.controller.services.events_service.JSON_EVENT_ADAPTER_CLASSES",
        tuple(_MinimalJsonAdapter for _ in JSON_EVENT_ADAPTER_CLASSES),
    )

    svc = EventsService()
    adapters = svc.build_event_adapters(
        params={},
        use_database=True,
        db_controller=_DbDisconnected(),
        db_adapter_cam_events=db_mock,
    )
    assert db_mock not in adapters
    assert len(adapters) == len(JSON_EVENT_ADAPTER_CLASSES)


def test_build_event_adapters_falls_back_image_dir(monkeypatch, tmp_path):
    seen_dirs = []

    class _FakeJsonAdapter:
        def __init__(self, _ctrl):
            pass

        def set_params(self, **kwargs):
            seen_dirs.append(kwargs.get("image_dir"))

        def init(self):
            return None

        def start(self):
            return None

        def get_event_name(self):
            return "fake_json"

    fake_tuple = tuple(_FakeJsonAdapter for _ in JSON_EVENT_ADAPTER_CLASSES)
    monkeypatch.setattr(
        "evileye.controller.services.events_service.JSON_EVENT_ADAPTER_CLASSES",
        fake_tuple,
    )
    monkeypatch.delenv("EVILEYE_DATA_DIR", raising=False)

    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    bad_dir = str(blocker / "EvilEyeData")
    fallback = tmp_path / "local_data"

    from evileye.utils.database_config_utils import resolve_writable_image_dir as _real_resolve

    def _resolve(preferred, **kwargs):
        return _real_resolve(preferred, fallback=str(fallback))

    monkeypatch.setattr(
        "evileye.utils.database_config_utils.resolve_writable_image_dir",
        _resolve,
    )

    svc = EventsService()
    params = {"database": {"image_dir": bad_dir}}
    adapters = svc.build_event_adapters(
        params=params,
        use_database=False,
        db_controller=None,
    )
    assert len(adapters) == len(JSON_EVENT_ADAPTER_CLASSES)
    assert all(d == str(fallback.resolve()) for d in seen_dirs)
    assert params["database"]["image_dir"] == str(fallback.resolve())
