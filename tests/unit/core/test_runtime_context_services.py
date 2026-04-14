import warnings

import evileye.api.core.broker_access as broker_access
import evileye.api.core.manager_access as manager_access
from evileye.api.core.broker_access import get_broker
from evileye.api.core.manager_access import get_manager
from evileye.core.process_manager import get_process_manager
from evileye.core.runtime_context import reset_runtime_context, get_or_create_runtime_service
from evileye.core.runtime_services import get_frame_broker, get_pipeline_manager


def test_runtime_services_are_singletons_in_context():
    reset_runtime_context()
    b1 = get_broker()
    b2 = get_broker()
    m1 = get_manager()
    m2 = get_manager()
    p1 = get_process_manager()
    p2 = get_process_manager()
    assert b1 is b2
    assert m1 is m2
    assert p1 is p2


def test_runtime_services_recreated_after_reset():
    reset_runtime_context()
    old_broker = get_broker()
    reset_runtime_context()
    new_broker = get_broker()
    assert old_broker is not new_broker


def test_get_or_create_runtime_service_caches_instance():
    reset_runtime_context()
    created = []

    def _factory():
        created.append(1)
        return object()

    s1 = get_or_create_runtime_service("broker", _factory)
    s2 = get_or_create_runtime_service("broker", _factory)
    assert s1 is s2
    assert len(created) == 1


def test_runtime_services_wrappers_use_same_context_instances():
    reset_runtime_context()
    assert get_frame_broker() is get_broker()
    assert get_pipeline_manager() is get_manager()


def test_compat_accessors_emit_deprecation_warning_once():
    reset_runtime_context()
    broker_access._DEPRECATION_WARNED = False
    manager_access._DEPRECATION_WARNED = False
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        _ = get_broker()
        _ = get_broker()
        _ = get_manager()
        _ = get_manager()
    deprecations = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    # One warning for broker facade and one for manager facade.
    assert len(deprecations) == 2
