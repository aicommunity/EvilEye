from pathlib import Path

import pytest

from evileye.api.core.ssl_files import SslConfigError, apply_ssl_env, resolve_ssl_files, ssl_enabled

_CERT = "-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n"
_KEY = "-----BEGIN PRIVATE KEY-----\nMIIB\n-----END PRIVATE KEY-----\n"


def _write_pair(root: Path) -> tuple[Path, Path]:
    certs = root / "certs"
    certs.mkdir()
    cert = certs / "server.crt"
    key = certs / "server.key"
    cert.write_text(_CERT, encoding="utf-8")
    key.write_text(_KEY, encoding="utf-8")
    return cert, key


def test_resolve_relative_paths_from_site_root(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("EVILEYE_SSL_CERTFILE", raising=False)
    monkeypatch.delenv("EVILEYE_SSL_KEYFILE", raising=False)
    _write_pair(tmp_path)
    cert, key = resolve_ssl_files(
        server_cfg={"ssl_certfile": "certs/server.crt", "ssl_keyfile": "certs/server.key"},
        site_dir=tmp_path,
    )
    assert cert == (tmp_path / "certs" / "server.crt").resolve()
    assert key == (tmp_path / "certs" / "server.key").resolve()
    assert ssl_enabled(cert, key)


def test_resolve_ssl_merges_system_json_when_pipeline_server_has_no_ssl(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("EVILEYE_SSL_CERTFILE", raising=False)
    monkeypatch.delenv("EVILEYE_SSL_KEYFILE", raising=False)
    _write_pair(tmp_path)
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs" / "system.json").write_text(
        '{"server": {"ssl_certfile": "certs/server.crt", "ssl_keyfile": "certs/server.key"}}',
        encoding="utf-8",
    )
    cert, key = resolve_ssl_files(
        server_cfg={"enabled": True, "host": "0.0.0.0", "port": 8181},
        site_dir=tmp_path,
    )
    assert cert == (tmp_path / "certs" / "server.crt").resolve()
    assert key == (tmp_path / "certs" / "server.key").resolve()


def test_half_pair_raises(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("EVILEYE_SSL_CERTFILE", raising=False)
    monkeypatch.delenv("EVILEYE_SSL_KEYFILE", raising=False)
    cert, _ = _write_pair(tmp_path)
    with pytest.raises(SslConfigError, match="Both ssl_certfile"):
        resolve_ssl_files(cli_cert=str(cert), cli_key=None, site_dir=tmp_path)


def test_apply_ssl_env_sets_cafile(tmp_path: Path):
    import os

    cert, key = _write_pair(tmp_path)
    ca = tmp_path / "certs" / "ca.crt"
    ca.write_text(_CERT, encoding="utf-8")
    old = {name: os.environ.get(name) for name in ("EVILEYE_SSL_CERTFILE", "EVILEYE_SSL_KEYFILE", "EVILEYE_SSL_CAFILE")}
    try:
        for name in old:
            os.environ.pop(name, None)
        apply_ssl_env(cert, key)
        assert os.environ["EVILEYE_SSL_CERTFILE"] == str(cert.resolve())
        assert os.environ["EVILEYE_SSL_KEYFILE"] == str(key.resolve())
        assert os.environ["EVILEYE_SSL_CAFILE"] == str(ca.resolve())
    finally:
        for name, value in old.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
