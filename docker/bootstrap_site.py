#!/usr/bin/env python3
"""Bootstrap an EvilEye site directory from container image."""
from __future__ import annotations

import json
import os
import shutil
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


def _copy_package_file(relpath: str, dst: Path) -> None:
    from importlib import resources

    src = resources.files("evileye").joinpath(relpath)
    dst.write_bytes(src.read_bytes())


def _ensure_dirs(site: Path) -> None:
    for rel in ("EvilEyeData/images", "videos", "models", "configs", "logs", "postgres_data", "bin"):
        (site / rel).mkdir(parents=True, exist_ok=True)


def _ensure_credentials(site: Path) -> None:
    creds = site / "credentials.json"
    if creds.exists():
        return
    _copy_package_file("credentials_proto.json", creds)
    payload = json.loads(creds.read_text(encoding="utf-8"))
    db = payload.setdefault("database", {})
    db.setdefault("user_name", "postgres")
    db.setdefault("password", "postgres")
    db.setdefault("database_name", "evil_eye_db")
    db["host_name"] = "db"
    db.setdefault("port", 5432)
    db.setdefault("admin_user_name", "postgres")
    db.setdefault("admin_password", "postgres")
    creds.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _ensure_sample_config(site: Path) -> None:
    cfg = site / "configs" / "single_video.json"
    if cfg.exists():
        return
    _copy_package_file("samples_configs/single_video.json", cfg)


def _write_site_compose(site: Path, image: str) -> None:
    template_name = "compose.site.cpu.yml" if image.endswith(":cpu") else "compose.site.gpu.yml"
    template = Path("/opt/evileye/docker") / template_name
    payload = template.read_text(encoding="utf-8").replace("__EVILEYE_IMAGE__", image)
    (site / "docker-compose.yml").write_text(payload, encoding="utf-8")


def _write_env(site: Path, image: str) -> None:
    env = site / ".env"
    if env.exists():
        return
    env.write_text(
        "\n".join(
            [
                f"EVILEYE_IMAGE={image}",
                "EVILEYE_HOST_PORT=8181",
                "EVILEYE_PG_PORT=5432",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _cpu_gpu_export_bash(image: str) -> str:
    if image.endswith(":cpu"):
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

    cpu = image.endswith(":cpu")
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


def main() -> int:
    target = os.environ.get("EVILEYE_BOOTSTRAP_TARGET", "/site").strip() or "/site"
    image = os.environ.get("EVILEYE_BOOTSTRAP_IMAGE", "evileye/app:latest").strip() or "evileye/app:latest"
    site = Path(target).expanduser().resolve()
    site.mkdir(parents=True, exist_ok=True)

    _ensure_dirs(site)
    _ensure_credentials(site)
    _ensure_sample_config(site)
    _write_site_compose(site, image)
    _write_env(site, image)
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
