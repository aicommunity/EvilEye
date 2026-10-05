#!/usr/bin/env python3
"""Bootstrap an EvilEye site directory from container image."""
from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import string
from pathlib import Path

HOST_CLI_COMMANDS = (
    ("evileye", "evileye"),
    ("evileye-launch", "evileye-launch"),
    ("evileye-process", "evileye-process"),
    ("evileye-configure", "evileye-configure"),
    ("evileye-srv", "evileye-srv"),
)

HOST_CLI_SRC = Path("/opt/evileye/docker/host-cli")
HOST_CLI_WIN_SRC = HOST_CLI_SRC / "windows"


def is_cpu_image(image: str) -> bool:
    """True for tags ending with :cpu or *-cpu (e.g. 0.0.15-cpu)."""
    tag = image.rsplit("/", 1)[-1]
    if ":" in tag:
        tag = tag.split(":", 1)[1]
    return tag == "cpu" or tag.endswith("-cpu")


def _copy_package_file(relpath: str, dst: Path) -> None:
    from importlib import resources

    src = resources.files("evileye").joinpath(relpath)
    dst.write_bytes(src.read_bytes())


def _ensure_dirs(site: Path) -> None:
    for rel in ("EvilEyeData/images", "videos", "models", "configs", "logs", "postgres_data", "bin"):
        (site / rel).mkdir(parents=True, exist_ok=True)


def _fill_db_password(db: dict, password: str) -> None:
    if not db.get("password"):
        db["password"] = password
    if not db.get("admin_password"):
        db["admin_password"] = db.get("password") or password


def _ensure_credentials(site: Path, postgres_password: str) -> None:
    creds = site / "credentials.json"
    if creds.exists():
        payload = json.loads(creds.read_text(encoding="utf-8"))
        db = payload.setdefault("database", {})
        db["host_name"] = "db"
        _fill_db_password(db, postgres_password)
        creds.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return
    _copy_package_file("credentials_proto.json", creds)
    payload = json.loads(creds.read_text(encoding="utf-8"))
    db = payload.setdefault("database", {})
    db["user_name"] = db.get("user_name") or "postgres"
    db["database_name"] = db.get("database_name") or "evil_eye_db"
    db["host_name"] = "db"
    db["port"] = db.get("port") or 5432
    db["admin_user_name"] = db.get("admin_user_name") or "postgres"
    _fill_db_password(db, postgres_password)
    creds.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _ensure_sample_config(site: Path) -> None:
    cfg = site / "configs" / "single_video.json"
    if cfg.exists():
        return
    _copy_package_file("samples_configs/single_video.json", cfg)


def _write_site_compose(site: Path, image: str, force: bool) -> None:
    compose_path = site / "docker-compose.yml"
    template_name = "compose.site.cpu.yml" if is_cpu_image(image) else "compose.site.gpu.yml"
    template = Path("/opt/evileye/docker") / template_name
    payload = template.read_text(encoding="utf-8")
    # Templates already use ${EVILEYE_IMAGE:-...}; keep as-is.
    if compose_path.exists() and not force:
        print("docker-compose.yml already exists, skipping (set EVILEYE_BOOTSTRAP_FORCE=1 to overwrite)")
        return
    if compose_path.exists() and force:
        bak = site / "docker-compose.yml.bak"
        shutil.copy2(compose_path, bak)
        print("Backed up existing docker-compose.yml ->", bak)
    compose_path.write_text(payload, encoding="utf-8")


def _generate_password(length: int = 24) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _read_env_password(env_path: Path) -> str | None:
    if not env_path.exists():
        return None
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("POSTGRES_PASSWORD="):
            value = line.split("=", 1)[1].strip().strip('"').strip("'")
            return value or None
    return None


def _read_credentials_password(site: Path) -> str | None:
    creds = site / "credentials.json"
    if not creds.exists():
        return None
    try:
        payload = json.loads(creds.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    db = payload.get("database") or {}
    for key in ("password", "admin_password"):
        value = db.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _write_env(site: Path, image: str, postgres_password: str, force: bool) -> None:
    env = site / ".env"
    lines = [
        f"EVILEYE_IMAGE={image}",
        "EVILEYE_HOST_PORT=8181",
        "EVILEYE_PG_PORT=5432",
        f"POSTGRES_PASSWORD={postgres_password}",
        "",
    ]
    text = "\n".join(lines)
    if env.exists() and not force:
        # Ensure POSTGRES_PASSWORD is present; do not overwrite other keys blindly.
        existing = env.read_text(encoding="utf-8")
        if "POSTGRES_PASSWORD=" not in existing:
            with env.open("a", encoding="utf-8") as fh:
                fh.write(f"\nPOSTGRES_PASSWORD={postgres_password}\n")
        if "EVILEYE_IMAGE=" not in existing:
            with env.open("a", encoding="utf-8") as fh:
                fh.write(f"\nEVILEYE_IMAGE={image}\n")
        print(".env already exists, skipping full rewrite")
        return
    if env.exists() and force:
        shutil.copy2(env, site / ".env.bak")
    env.write_text(text, encoding="utf-8")


def _cpu_gpu_export_bash(image: str) -> str:
    if is_cpu_image(image):
        return 'export EVILEYE_DOCKER_GPU_MODE="${EVILEYE_DOCKER_GPU_MODE:-none}"\n'
    return ""


def _write_bash_host_cli(bin_dir: Path, image: str) -> None:
    launcher_src = HOST_CLI_SRC / "evileye-docker-run.sh"
    if not launcher_src.is_file():
        print("warning: missing", launcher_src, "- skip bash host-cli")
        return
    shutil.copy2(launcher_src, bin_dir / "evileye-docker-run.sh")
    os.chmod(bin_dir / "evileye-docker-run.sh", 0o755)

    gpu_line = _cpu_gpu_export_bash(image)
    for name, cmd in HOST_CLI_COMMANDS:
        script = (
            "#!/usr/bin/env bash\n"
            "# EvilEye docker host-cli\n"
            "set -euo pipefail\n"
            f'export EVILEYE_DOCKER_IMAGE="${{EVILEYE_DOCKER_IMAGE:-{image}}}"\n'
            f"{gpu_line}"
            'export EVILEYE_DOCKER_SITE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"\n'
            'ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n'
            f'exec "$ROOT/evileye-docker-run.sh" {cmd} "$@"\n'
        )
        path = bin_dir / name
        path.write_text(script, encoding="utf-8")
        os.chmod(path, 0o755)


def _write_windows_host_cli(bin_dir: Path, image: str) -> None:
    if not HOST_CLI_WIN_SRC.is_dir():
        print("warning: missing", HOST_CLI_WIN_SRC, "- skip Windows host-cli")
        return

    launcher_src = HOST_CLI_WIN_SRC / "EvilEye-DockerRun.ps1"
    if not launcher_src.is_file():
        print("warning: missing", launcher_src, "- skip Windows host-cli")
        return
    shutil.copy2(launcher_src, bin_dir / "EvilEye-DockerRun.ps1")

    cpu = is_cpu_image(image)
    for name, cmd in HOST_CLI_COMMANDS:
        lines = [
            "#Requires -Version 5.1",
            "# EvilEye docker host-cli",
            "$ErrorActionPreference = 'Stop'",
            "$Root = $PSScriptRoot",
            f"if (-not $env:EVILEYE_DOCKER_IMAGE) {{ $env:EVILEYE_DOCKER_IMAGE = '{image}' }}",
        ]
        if cpu:
            lines.append(
                "if (-not $env:EVILEYE_DOCKER_GPU_MODE) { $env:EVILEYE_DOCKER_GPU_MODE = 'none' }"
            )
        lines.extend(
            [
                "$env:EVILEYE_DOCKER_SITE_DIR = (Resolve-Path (Join-Path $Root '..')).Path",
                "$Launcher = Join-Path $Root 'EvilEye-DockerRun.ps1'",
                f"& $Launcher '{cmd}' @args",
                "exit $LASTEXITCODE",
                "",
            ]
        )
        (bin_dir / f"{name}.ps1").write_text("\n".join(lines), encoding="utf-8", newline="\r\n")

        cmd_text = (
            "@echo off\r\n"
            "rem EvilEye docker host-cli\r\n"
            "setlocal\r\n"
            'set "SCRIPT_DIR=%~dp0"\r\n'
            f'powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%{name}.ps1" %*\r\n'
            "exit /b %ERRORLEVEL%\r\n"
        )
        (bin_dir / f"{name}.cmd").write_text(cmd_text, encoding="utf-8", newline="")


def _write_host_cli(site: Path, image: str) -> None:
    bin_dir = site / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    _write_bash_host_cli(bin_dir, image)
    _write_windows_host_cli(bin_dir, image)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap EvilEye site directory")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite docker-compose.yml and .env (backs up to *.bak)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    force = args.force or os.environ.get("EVILEYE_BOOTSTRAP_FORCE", "").strip() in ("1", "true", "yes")
    target = os.environ.get("EVILEYE_BOOTSTRAP_TARGET", "/site").strip() or "/site"
    image = os.environ.get("EVILEYE_BOOTSTRAP_IMAGE", "evileye/app:latest").strip() or "evileye/app:latest"
    site = Path(target).expanduser().resolve()
    site.mkdir(parents=True, exist_ok=True)

    env_path = site / ".env"
    postgres_password = (
        os.environ.get("POSTGRES_PASSWORD", "").strip()
        or _read_env_password(env_path)
        or _read_credentials_password(site)
        or _generate_password()
    )

    _ensure_dirs(site)
    _ensure_credentials(site, postgres_password)
    _ensure_sample_config(site)
    _write_site_compose(site, image, force=force)
    _write_env(site, image, postgres_password, force=force)
    _write_host_cli(site, image)

    print("Bootstrap complete:", site)
    print("Next steps:")
    print("  docker compose up -d")
    print("  # Linux/macOS / Git Bash:")
    print('  export PATH="$PWD/bin:$PATH"')
    print("  # Windows PowerShell:")
    print('  $env:Path = "$PWD\\bin;$env:Path"')
    print("  evileye --help")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
