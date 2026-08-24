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
    assert (
        canonicalize_relay_base_url("https://0.0.0.0:8181/api/v1")
        == "https://127.0.0.1:8181/api/v1"
    )


def test_resolve_public_api_base_url_defaults_to_loopback(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("EVILEYE_WEB_API_BASE", raising=False)
    monkeypatch.delenv("EVILEYE_SSL_CERTFILE", raising=False)
    monkeypatch.delenv("EVILEYE_SSL_KEYFILE", raising=False)
    monkeypatch.delenv("EVILEYE_SITE_DIR", raising=False)
    assert resolve_public_api_base_url(port=8181) == "http://127.0.0.1:8181/api/v1"


def test_resolve_public_api_base_url_https_when_ssl_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cert = tmp_path / "server.crt"
    key = tmp_path / "server.key"
    cert.write_text("-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n", encoding="utf-8")
    key.write_text("-----BEGIN PRIVATE KEY-----\nMIIB\n-----END PRIVATE KEY-----\n", encoding="utf-8")
    monkeypatch.setenv("EVILEYE_SSL_CERTFILE", str(cert))
    monkeypatch.setenv("EVILEYE_SSL_KEYFILE", str(key))
    monkeypatch.delenv("EVILEYE_WEB_API_BASE", raising=False)
    assert resolve_public_api_base_url(port=8181) == "https://127.0.0.1:8181/api/v1"
