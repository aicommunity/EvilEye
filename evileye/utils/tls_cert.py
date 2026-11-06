"""Generate a local mini-CA and SAN leaf certificate via openssl."""
from __future__ import annotations

import shutil
import stat
import subprocess
import tempfile
import os
import re
from pathlib import Path
from typing import Sequence


class TlsCertError(RuntimeError):
    pass


def openssl_bin() -> str:
    candidates: list[str] = []
    found = shutil.which("openssl")
    if found:
        candidates.append(found)

    # Windows PATHs often contain the 2008 GnuWin32 OpenSSL before Git for
    # Windows. That build is too old for current TLS workflows and points its
    # default config at /usr/local/ssl/openssl.cnf. Prefer a maintained install.
    if os.name == "nt":
        roots = [
            os.environ.get("ProgramFiles"),
            os.environ.get("ProgramFiles(x86)"),
        ]
        for root in filter(None, roots):
            candidates.extend(
                [
                    str(Path(root) / "Git" / "usr" / "bin" / "openssl.exe"),
                    str(Path(root) / "OpenSSL-Win64" / "bin" / "openssl.exe"),
                ]
            )

    seen: set[str] = set()
    for candidate in candidates:
        normalized = os.path.normcase(os.path.abspath(candidate))
        if normalized in seen or not Path(candidate).is_file():
            continue
        seen.add(normalized)
        try:
            result = subprocess.run(
                [candidate, "version"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        version = re.search(r"(?:OpenSSL|LibreSSL)\s+(\d+)\.(\d+)\.(\d+)", result.stdout)
        if result.returncode == 0 and version:
            parsed = tuple(int(part) for part in version.groups())
            if parsed >= (1, 1, 1):
                return candidate

    if not candidates:
        raise TlsCertError(
            "openssl not found on PATH. Install OpenSSL (Linux) or Git for Windows, "
            "then retry HTTPS setup."
        )
    raise TlsCertError(
        "A supported OpenSSL (1.1.1 or newer) was not found. Install a current "
        "OpenSSL release or Git for Windows, then retry HTTPS setup."
    )


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise TlsCertError(f"openssl failed ({' '.join(cmd[:3])}…): {detail}")


def _chmod_private(path: Path) -> None:
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def generate_minica_leaf(
    out_dir: Path,
    *,
    ips: Sequence[str] = (),
    dns_names: Sequence[str] = (),
    days: int = 825,
    force: bool = False,
    openssl: str | None = None,
) -> dict[str, Path]:
    """Create certs/ca.crt + server.crt/key. SAN must include at least one IP or DNS name."""
    ips_clean = [str(v).strip() for v in ips if str(v).strip()]
    dns_clean = [str(v).strip() for v in dns_names if str(v).strip()]
    if not ips_clean and not dns_clean:
        raise TlsCertError("At least one SAN IP or DNS name is required.")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "ca_key": out_dir / "ca.key",
        "ca_crt": out_dir / "ca.crt",
        "server_key": out_dir / "server.key",
        "server_crt": out_dir / "server.crt",
    }
    if not force and any(p.exists() for p in paths.values()):
        raise TlsCertError(f"Certificate files already exist in {out_dir}. Use --tls-force to replace.")

    binary = openssl or openssl_bin()
    cn = dns_clean[0] if dns_clean else ips_clean[0]
    san_parts = [f"IP:{ip}" for ip in ips_clean] + [f"DNS:{name}" for name in dns_clean]
    san_line = "subjectAltName=" + ",".join(san_parts)

    with tempfile.TemporaryDirectory(prefix="evileye-tls-") as tmp:
        tmp_path = Path(tmp)
        ext = tmp_path / "leaf.ext"
        ext.write_text("basicConstraints=CA:FALSE\nkeyUsage=digitalSignature,keyEncipherment\n" + san_line + "\n", encoding="utf-8")
        csr = tmp_path / "server.csr"
        serial = tmp_path / "ca.srl"
        _run([binary, "genrsa", "-out", str(paths["ca_key"]), "4096"])
        _run(
            [
                binary,
                "req",
                "-x509",
                "-new",
                "-nodes",
                "-key",
                str(paths["ca_key"]),
                "-sha256",
                "-days",
                "3650",
                "-subj",
                "/CN=EvilEye Local CA",
                "-out",
                str(paths["ca_crt"]),
            ]
        )
        _run([binary, "genrsa", "-out", str(paths["server_key"]), "2048"])
        _run(
            [
                binary,
                "req",
                "-new",
                "-key",
                str(paths["server_key"]),
                "-subj",
                f"/CN={cn}",
                "-out",
                str(csr),
            ]
        )
        _run(
            [
                binary,
                "x509",
                "-req",
                "-in",
                str(csr),
                "-CA",
                str(paths["ca_crt"]),
                "-CAkey",
                str(paths["ca_key"]),
                "-CAcreateserial",
                "-CAserial",
                str(serial),
                "-out",
                str(paths["server_crt"]),
                "-days",
                str(int(days)),
                "-sha256",
                "-extfile",
                str(ext),
            ]
        )
    _chmod_private(paths["ca_key"])
    _chmod_private(paths["server_key"])
    return paths
