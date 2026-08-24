"""HTTPS setup step for `evileye install-server` (interactive or flag-driven)."""
from __future__ import annotations

import json
import socket
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from rich.console import Console
from rich.prompt import Confirm, Prompt

from evileye.api.core.ssl_files import SslConfigError, load_system_server_cfg, resolve_ssl_files
from evileye.core.paths import configs_dir
from evileye.utils.tls_cert import TlsCertError, generate_minica_leaf


@dataclass
class TlsWizardResult:
    enabled: bool
    certfile: Optional[Path] = None
    keyfile: Optional[Path] = None
    cafile: Optional[Path] = None
    public_base_url: Optional[str] = None
    message: str = ""


def guess_lan_ipv4() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        return str(ip or "")
    except OSError:
        return ""
    finally:
        sock.close()


def _server_port(site_dir: Path) -> int:
    cfg = load_system_server_cfg(site_dir)
    try:
        return int(cfg.get("port") or 8181)
    except (TypeError, ValueError):
        return 8181


def patch_system_ssl(
    site_dir: Path,
    *,
    certfile: Path | None,
    keyfile: Path | None,
    public_base_url: str | None = None,
    clear: bool = False,
) -> None:
    """Merge TLS paths into configs/system.json without rewriting unrelated keys.

    Never touches credentials.json (users/passwords). If system.json exists but
    is not valid JSON, raise instead of replacing the file.
    """
    path = configs_dir(site_dir) / "system.json"
    payload: dict
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise SslConfigError(
                f"Cannot update TLS settings: {path} is not valid JSON ({exc}). "
                "Fix the file; install-server will not overwrite it."
            ) from exc
        if not isinstance(loaded, dict):
            raise SslConfigError(f"Cannot update TLS settings: {path} root must be a JSON object.")
        payload = loaded
    else:
        payload = {}
    server = payload.get("server")
    if not isinstance(server, dict):
        server = {}
        payload["server"] = server
    if clear or certfile is None or keyfile is None:
        server.pop("ssl_certfile", None)
        server.pop("ssl_keyfile", None)
    else:
        try:
            rel_cert = certfile.resolve().relative_to(site_dir.resolve())
            rel_key = keyfile.resolve().relative_to(site_dir.resolve())
            server["ssl_certfile"] = str(rel_cert).replace("\\", "/")
            server["ssl_keyfile"] = str(rel_key).replace("\\", "/")
        except ValueError:
            server["ssl_certfile"] = str(certfile.resolve())
            server["ssl_keyfile"] = str(keyfile.resolve())
    if public_base_url:
        existing = str(server.get("public_base_url") or "").strip()
        if not existing:
            server["public_base_url"] = public_base_url.rstrip("/")
        elif existing.startswith("http://") and public_base_url.startswith("https://"):
            server["public_base_url"] = public_base_url.rstrip("/")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _existing_tls(site_dir: Path) -> tuple[Path | None, Path | None]:
    try:
        return resolve_ssl_files(site_dir=site_dir, server_cfg=load_system_server_cfg(site_dir))
    except SslConfigError:
        return None, None


def _public_url(host: str, port: int) -> str:
    return f"https://{host}:{port}"


def print_https_hints(console: Console, result: TlsWizardResult) -> None:
    if result.message:
        style = "green" if result.enabled else "yellow"
        console.print(f"[{style}]{result.message}[/{style}]")
    if not result.enabled:
        return
    url = result.public_base_url
    if url:
        console.print(f"[green]HTTPS Web UI:[/green] {url}")
        console.print(
            f"[dim]If you open the UI from a LAN IP or custom name, set "
            f"EVILEYE_CORS_ALLOW_ORIGINS={url}[/dim]"
        )
    if result.cafile and result.cafile.is_file():
        console.print(
            f"[blue]Trust the local CA on clients (optional):[/blue] {result.cafile}\n"
            "Until then browsers will warn about a self-signed certificate."
        )


def run_tls_deploy_step(
    *,
    site_dir: Path,
    console: Console,
    no_tls: bool = False,
    non_interactive: bool = False,
    tls_self_signed: bool = False,
    tls_ips: Sequence[str] = (),
    tls_dns: Sequence[str] = (),
    ssl_certfile: str | None = None,
    ssl_keyfile: str | None = None,
    tls_force: bool = False,
) -> TlsWizardResult:
    site_dir = Path(site_dir).resolve()
    interactive = (not non_interactive) and sys.stdin.isatty() and sys.stdout.isatty()
    port = _server_port(site_dir)
    existing_c, existing_k = _existing_tls(site_dir)

    if no_tls:
        if existing_c or existing_k:
            patch_system_ssl(site_dir, certfile=None, keyfile=None, clear=True)
        return TlsWizardResult(enabled=False, message="TLS skipped (--no-tls). Web UI will use HTTP.")

    if ssl_certfile or ssl_keyfile:
        cert, key = resolve_ssl_files(cli_cert=ssl_certfile, cli_key=ssl_keyfile, site_dir=site_dir)
        assert cert and key
        host = (tls_dns[0] if tls_dns else (tls_ips[0] if tls_ips else "127.0.0.1"))
        url = _public_url(host, port)
        patch_system_ssl(site_dir, certfile=cert, keyfile=key, public_base_url=url)
        return TlsWizardResult(enabled=True, certfile=cert, keyfile=key, public_base_url=url, message=f"Using existing certificate {cert}")

    if tls_self_signed:
        ips = [v.strip() for v in tls_ips if str(v).strip()] or ["127.0.0.1"]
        dns = [v.strip() for v in tls_dns if str(v).strip()]
        paths = generate_minica_leaf(site_dir / "certs", ips=ips, dns_names=dns, force=tls_force)
        host = dns[0] if dns else ips[0]
        url = _public_url(host, port)
        patch_system_ssl(site_dir, certfile=paths["server_crt"], keyfile=paths["server_key"], public_base_url=url)
        return TlsWizardResult(
            enabled=True,
            certfile=paths["server_crt"],
            keyfile=paths["server_key"],
            cafile=paths["ca_crt"],
            public_base_url=url,
            message=f"Issued self-signed certificate for {host}",
        )

    if not interactive:
        return TlsWizardResult(
            enabled=False,
            message="TLS not configured (non-interactive). Re-run `evileye install-server` in a terminal to enable HTTPS.",
        )

    if existing_c and existing_k:
        choice = Prompt.ask(
            "HTTPS is already configured. Keep / Replace / Disable",
            choices=["keep", "replace", "disable"],
            default="keep",
        )
        if choice == "keep":
            return TlsWizardResult(enabled=True, certfile=existing_c, keyfile=existing_k, message="Keeping existing HTTPS certificate.")
        if choice == "disable":
            patch_system_ssl(site_dir, certfile=None, keyfile=None, clear=True)
            return TlsWizardResult(enabled=False, message="HTTPS disabled. Web UI will use HTTP.")
        tls_force = True

    if not Confirm.ask("Enable HTTPS for the Web UI?", default=False):
        return TlsWizardResult(enabled=False, message="HTTPS not enabled.")

    mode = Prompt.ask(
        "Certificate source",
        choices=["self-signed", "existing"],
        default="self-signed",
    )
    if mode == "existing":
        cert_raw = Prompt.ask("Path to TLS certificate (PEM)")
        key_raw = Prompt.ask("Path to TLS private key (PEM)")
        cert, key = resolve_ssl_files(cli_cert=cert_raw, cli_key=key_raw, site_dir=site_dir)
        assert cert and key
        host = Prompt.ask("Public host for the UI (IP or DNS name)", default="127.0.0.1")
        url = _public_url(host.strip() or "127.0.0.1", port)
        patch_system_ssl(site_dir, certfile=cert, keyfile=key, public_base_url=url)
        return TlsWizardResult(enabled=True, certfile=cert, keyfile=key, public_base_url=url, message=f"Using certificate {cert}")

    console.print("[dim]Browsers will warn until clients import certs/ca.crt as a trusted CA.[/dim]")
    ips: list[str] = []
    dns: list[str] = []
    guessed = guess_lan_ipv4()
    if Confirm.ask("Issue the certificate for one or more IP addresses?", default=True):
        default_ips = ",".join([p for p in (guessed, "127.0.0.1") if p])
        raw = Prompt.ask("IP addresses (comma-separated)", default=default_ips or "127.0.0.1")
        ips = [part.strip() for part in raw.split(",") if part.strip()]
        if "127.0.0.1" not in ips and Confirm.ask("Also include 127.0.0.1?", default=True):
            ips.append("127.0.0.1")
    if Confirm.ask("Issue the certificate for a local DNS name?", default=False):
        console.print("[dim]Add the name to /etc/hosts (or LAN DNS) on each client, e.g. 192.168.1.50 evileye.lan[/dim]")
        raw = Prompt.ask("DNS names (comma-separated)", default="evileye.lan")
        dns = [part.strip() for part in raw.split(",") if part.strip()]
    if not ips and not dns:
        raise TlsCertError("At least one IP or DNS name is required for the certificate SAN.")
    paths = generate_minica_leaf(site_dir / "certs", ips=ips, dns_names=dns, force=tls_force)
    host = dns[0] if dns else ips[0]
    url = _public_url(host, port)
    patch_system_ssl(site_dir, certfile=paths["server_crt"], keyfile=paths["server_key"], public_base_url=url)
    return TlsWizardResult(
        enabled=True,
        certfile=paths["server_crt"],
        keyfile=paths["server_key"],
        cafile=paths["ca_crt"],
        public_base_url=url,
        message=f"Issued self-signed certificate for {host}",
    )
