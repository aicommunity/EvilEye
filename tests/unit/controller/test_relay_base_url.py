from evileye.api.core.public_base_url import canonicalize_relay_base_url, resolve_public_api_base_url


def test_canonicalize_relay_base_url_replaces_bind_all():
    assert (
        canonicalize_relay_base_url("http://0.0.0.0:8181/api/v1")
        == "http://127.0.0.1:8181/api/v1"
    )
    assert (
        canonicalize_relay_base_url("http://[::]:8181/api/v1")
        == "http://127.0.0.1:8181/api/v1"
    )


def test_resolve_public_api_base_url_defaults_to_loopback():
    assert resolve_public_api_base_url(port=8181) == "http://127.0.0.1:8181/api/v1"
