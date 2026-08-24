from io import StringIO
import json
from pathlib import Path
import shutil

import pytest
from rich.console import Console

from evileye.utils.tls_deploy_wizard import run_tls_deploy_step


def _console() -> Console:
    return Console(file=StringIO())


def test_no_tls_skips_https(tmp_path: Path):
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs" / "system.json").write_text(json.dumps({"server": {"port": 8181}}), encoding="utf-8")
    result = run_tls_deploy_step(
        site_dir=tmp_path,
        console=_console(),
        no_tls=True,
        non_interactive=True,
    )
    assert result.enabled is False
    payload = json.loads((tmp_path / "configs" / "system.json").read_text(encoding="utf-8"))
    assert "ssl_certfile" not in payload.get("server", {})


@pytest.mark.skipif(shutil.which("openssl") is None, reason="openssl not on PATH")
def test_tls_self_signed_non_interactive(tmp_path: Path):
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs" / "system.json").write_text(json.dumps({"server": {"port": 8181}}), encoding="utf-8")
    result = run_tls_deploy_step(
        site_dir=tmp_path,
        console=_console(),
        non_interactive=True,
        tls_self_signed=True,
        tls_ips=["127.0.0.1"],
        tls_force=True,
    )
    assert result.enabled is True
    assert result.certfile and result.certfile.is_file()
    payload = json.loads((tmp_path / "configs" / "system.json").read_text(encoding="utf-8"))
    assert payload["server"]["ssl_certfile"] == "certs/server.crt"
    assert payload["server"]["public_base_url"] == "https://127.0.0.1:8181"


def test_patch_system_ssl_preserves_existing_pipeline(tmp_path: Path):
    from evileye.utils.tls_deploy_wizard import patch_system_ssl

    (tmp_path / "configs").mkdir()
    (tmp_path / "certs").mkdir()
    cert = tmp_path / "certs" / "server.crt"
    key = tmp_path / "certs" / "server.key"
    cert.write_text("-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n", encoding="utf-8")
    key.write_text("-----BEGIN PRIVATE KEY-----\nMIIB\n-----END PRIVATE KEY-----\n", encoding="utf-8")
    original = {
        "pipeline": {"sources": [{"source_ids": [0]}]},
        "server": {"enabled": True, "port": 8181, "public_base_url": "https://keep.example:8181"},
    }
    (tmp_path / "configs" / "system.json").write_text(json.dumps(original), encoding="utf-8")
    patch_system_ssl(tmp_path, certfile=cert, keyfile=key, public_base_url="https://127.0.0.1:8181")
    payload = json.loads((tmp_path / "configs" / "system.json").read_text(encoding="utf-8"))
    assert payload["pipeline"]["sources"][0]["source_ids"] == [0]
    assert payload["server"]["ssl_certfile"] == "certs/server.crt"
    assert payload["server"]["public_base_url"] == "https://keep.example:8181"
