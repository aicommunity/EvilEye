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
