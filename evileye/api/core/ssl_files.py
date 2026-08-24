"""Resolve TLS certificate paths for the EvilEye web server."""
from __future__ import annotations

import json
import os
import ssl
from pathlib import Path
from typing import Any, Mapping, Optional
from urllib.parse import urlparse

from evileye.core.paths import configs_dir, site_root

_CERT_ENV = "EVILEYE_SSL_CERTFILE"
_KEY_ENV = "EVILEYE_SSL_KEYFILE"
_CA_ENV = "EVILEYE_SSL_CAFILE"


class SslConfigError(ValueError):
    """Raised when TLS paths are incomplete or files are missing."""


def ssl_enabled(cert: Path | str | None, key: Path | str | None) -> bool:
    return bool(cert) and bool(key)


def load_system_server_cfg(root: Optional[Path | str] = None) -> dict[str, Any]:
    path = configs_dir(root) / "system.json"
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    server = payload.get("server")
    return server if isinstance(server, dict) else {}


def _normalize_path(raw: str | Path | None, *, root: Path) -> Path | None:
    text = str(raw or "").strip()
    if not text:
        return None
    path = Path(text).expanduser()
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def _validate_pair(cert: Path | None, key: Path | None) -> tuple[Path | None, Path | None]:
    if cert is None and key is None:
        return None, None
    if cert is None or key is None:
        raise SslConfigError("Both ssl_certfile and ssl_keyfile must be set, or neither.")
    if not cert.is_file():
        raise SslConfigError(f"TLS certificate not found: {cert}")
    if not key.is_file():
        raise SslConfigError(f"TLS private key not found: {key}")
    cert_text = cert.read_text(encoding="utf-8", errors="replace")
    key_text = key.read_text(encoding="utf-8", errors="replace")
    if "BEGIN CERTIFICATE" not in cert_text and "BEGIN " not in cert_text:
        raise SslConfigError(f"TLS certificate does not look like PEM: {cert}")
    if "BEGIN" not in key_text:
        raise SslConfigError(f"TLS private key does not look like PEM: {key}")
    return cert, key


def resolve_ssl_files(
    *,
    cli_cert: str | Path | None = None,
    cli_key: str | Path | None = None,
    server_cfg: Optional[Mapping[str, Any]] = None,
    site_dir: Optional[Path | str] = None,
) -> tuple[Path | None, Path | None]:
    """Resolve cert/key with CLI → env → server config priority."""
    root = site_root(site_dir)
    cli_c = _normalize_path(cli_cert, root=root)
    cli_k = _normalize_path(cli_key, root=root)
    if cli_c or cli_k:
        return _validate_pair(cli_c, cli_k)

    env_c = _normalize_path(os.getenv(_CERT_ENV), root=root)
    env_k = _normalize_path(os.getenv(_KEY_ENV), root=root)
    if env_c or env_k:
        return _validate_pair(env_c, env_k)

    cfg = dict(server_cfg or ())
    if not cfg:
        cfg = load_system_server_cfg(root)
    cfg_c = _normalize_path(cfg.get("ssl_certfile"), root=root)
    cfg_k = _normalize_path(cfg.get("ssl_keyfile"), root=root)
    return _validate_pair(cfg_c, cfg_k)


def apply_ssl_env(cert: Path | str | None, key: Path | str | None) -> None:
    """Export TLS paths for cookie Secure-flag detection and relay CA lookup."""
    if not ssl_enabled(cert, key):
        return
    cert_path = Path(cert).resolve()
    key_path = Path(key).resolve()
    os.environ[_CERT_ENV] = str(cert_path)
    os.environ[_KEY_ENV] = str(key_path)
    ca = cert_path.parent / "ca.crt"
    if ca.is_file():
        os.environ.setdefault(_CA_ENV, str(ca))


def hsts_enabled(server_cfg: Optional[Mapping[str, Any]] = None) -> bool:
    env = (os.getenv("EVILEYE_HSTS") or "").strip().lower()
    if env in {"1", "true", "yes", "on"}:
        return True
    if env in {"0", "false", "no", "off"}:
        return False
    cfg = dict(server_cfg or ())
    if not cfg:
        cfg = load_system_server_cfg()
    return bool(cfg.get("hsts"))


def ssl_context_for_relay(url: str = "") -> ssl.SSLContext | None:
    """TLS context for runtime → API relay. Prefer local CA; loopback may skip verify."""
    if not str(url).lower().startswith("https://"):
        return None
    ca = (os.getenv(_CA_ENV) or "").strip()
    if ca and Path(ca).is_file():
        return ssl.create_default_context(cafile=ca)
    host = (urlparse(url).hostname or "").lower()
    if host in {"127.0.0.1", "localhost", "::1"}:
        return ssl._create_unverified_context()
    return ssl.create_default_context()
