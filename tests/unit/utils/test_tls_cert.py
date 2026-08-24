import shutil
import subprocess
from pathlib import Path

import pytest

from evileye.utils.tls_cert import TlsCertError, generate_minica_leaf

openssl = shutil.which("openssl")
pytestmark = pytest.mark.skipif(openssl is None, reason="openssl not on PATH")


def test_generate_minica_leaf_includes_ip_and_dns_san(tmp_path: Path):
    out = tmp_path / "certs"
    paths = generate_minica_leaf(out, ips=["127.0.0.1", "192.168.1.50"], dns_names=["evileye.lan"], force=True)
    text = subprocess.check_output(
        [openssl, "x509", "-in", str(paths["server_crt"]), "-noout", "-text"],
        text=True,
    )
    assert "IP Address:127.0.0.1" in text or "IP:127.0.0.1" in text
    assert "IP Address:192.168.1.50" in text or "IP:192.168.1.50" in text
    assert "DNS:evileye.lan" in text
    assert paths["server_key"].stat().st_mode & 0o077 == 0


def test_generate_requires_san(tmp_path: Path):
    with pytest.raises(TlsCertError, match="SAN"):
        generate_minica_leaf(tmp_path / "certs", ips=[], dns_names=[])
