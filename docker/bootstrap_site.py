#!/usr/bin/env python3
"""Bootstrap an EvilEye site directory from container image."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path


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


def _write_host_cli(site: Path, image: str) -> None:
    src_dir = Path("/opt/evileye/docker/host-cli")
    bin_dir = site / "bin"
    shutil.copy2(src_dir / "evileye-docker-run.sh", bin_dir / "evileye-docker-run.sh")
    os.chmod(bin_dir / "evileye-docker-run.sh", 0o755)

    wrappers = {
        "evileye": "evileye",
        "evileye-launch": "evileye-launch",
        "evileye-process": "evileye-process",
        "evileye-configure": "evileye-configure",
        "evileye-srv": "evileye-srv",
    }
    site_dir = str(site)
    for name, cmd in wrappers.items():
        script = (
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            f"export EVILEYE_DOCKER_IMAGE=\"${{EVILEYE_DOCKER_IMAGE:-{image}}}\"\n"
            f"export EVILEYE_DOCKER_SITE_DIR=\"${{EVILEYE_DOCKER_SITE_DIR:-{site_dir}}}\"\n"
            "ROOT=\"$(cd \"$(dirname \"${BASH_SOURCE[0]}\")\" && pwd)\"\n"
            f"exec \"$ROOT/evileye-docker-run.sh\" {cmd} \"$@\"\n"
        )
        path = bin_dir / name
        path.write_text(script, encoding="utf-8")
        os.chmod(path, 0o755)


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
    print("  export PATH=\"$PWD/bin:$PATH\"")
    print("  evileye --help")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
