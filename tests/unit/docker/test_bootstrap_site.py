"""Unit tests for docker/bootstrap_site.py (no Docker daemon required)."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
BOOTSTRAP_PATH = REPO_ROOT / "docker" / "bootstrap_site.py"
DOCKER_DIR = REPO_ROOT / "docker"


def _load_bootstrap():
    spec = importlib.util.spec_from_file_location("evileye_bootstrap_site", BOOTSTRAP_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def bootstrap(monkeypatch, tmp_path):
    mod = _load_bootstrap()
    # Point host-cli / templates at repo docker/ so bootstrap can copy wrappers.
    monkeypatch.setattr(mod, "HOST_CLI_SRC", DOCKER_DIR / "host-cli")
    monkeypatch.setattr(mod, "HOST_CLI_WIN_SRC", DOCKER_DIR / "host-cli" / "windows")

    def _write_site_compose_local(site: Path, image: str, force: bool) -> None:
        compose_path = site / "docker-compose.yml"
        template_name = "compose.site.cpu.yml" if mod.is_cpu_image(image) else "compose.site.gpu.yml"
        template = DOCKER_DIR / template_name
        payload = template.read_text(encoding="utf-8")
        if compose_path.exists() and not force:
            return
        if compose_path.exists() and force:
            import shutil

            shutil.copy2(compose_path, site / "docker-compose.yml.bak")
        compose_path.write_text(payload, encoding="utf-8")

    monkeypatch.setattr(mod, "_write_site_compose", _write_site_compose_local)
    # Avoid depending on installed package for credentials_proto in CI without editable install.
    proto = REPO_ROOT / "evileye" / "credentials_proto.json"
    sample = REPO_ROOT / "evileye" / "samples_configs" / "single_video.json"

    def _copy_package_file(relpath: str, dst: Path) -> None:
        mapping = {
            "credentials_proto.json": proto,
            "samples_configs/single_video.json": sample,
        }
        src = mapping[relpath]
        dst.write_bytes(src.read_bytes())

    monkeypatch.setattr(mod, "_copy_package_file", _copy_package_file)
    return mod


def test_is_cpu_image():
    mod = _load_bootstrap()
    assert mod.is_cpu_image("evileye/app:cpu")
    assert mod.is_cpu_image("evileye/app:0.0.15-cpu")
    assert not mod.is_cpu_image("evileye/app:latest")
    assert not mod.is_cpu_image("evileye/app:0.0.15")


def test_site_compose_templates_use_env_image():
    gpu = (DOCKER_DIR / "compose.site.gpu.yml").read_text(encoding="utf-8")
    cpu = (DOCKER_DIR / "compose.site.cpu.yml").read_text(encoding="utf-8")
    assert "${EVILEYE_IMAGE:-evileye/app:latest}" in gpu
    assert "${EVILEYE_IMAGE:-evileye/app:cpu}" in cpu
    assert "pg_isready" in gpu and "pg_isready" in cpu
    assert "service_healthy" in gpu and "service_healthy" in cpu
    assert "__EVILEYE_IMAGE__" not in gpu
    assert "__EVILEYE_IMAGE__" not in cpu


def test_repo_compose_defaults_point_to_parent():
    text = (DOCKER_DIR / "docker-compose.yml").read_text(encoding="utf-8")
    assert "${EVILEYE_SITE_DIR:-..}" in text
    assert "${EVILEYE_PG_DATA:-../postgres_data}" in text
    assert "name: evileye" in text
    assert "pg_isready" in text


def test_bootstrap_fills_empty_password(bootstrap, tmp_path, monkeypatch):
    monkeypatch.setenv("EVILEYE_BOOTSTRAP_TARGET", str(tmp_path))
    monkeypatch.setenv("EVILEYE_BOOTSTRAP_IMAGE", "evileye/app:latest")
    monkeypatch.setenv("POSTGRES_PASSWORD", "secret-db-pass")
    monkeypatch.delenv("EVILEYE_BOOTSTRAP_FORCE", raising=False)

    assert bootstrap.main([]) == 0

    creds = json.loads((tmp_path / "credentials.json").read_text(encoding="utf-8"))
    assert creds["database"]["password"] == "secret-db-pass"
    assert creds["database"]["admin_password"] == "secret-db-pass"
    assert creds["database"]["host_name"] == "db"

    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "POSTGRES_PASSWORD=secret-db-pass" in env_text
    assert "EVILEYE_IMAGE=evileye/app:latest" in env_text
    assert (tmp_path / "docker-compose.yml").is_file()
    assert "${EVILEYE_IMAGE:-" in (tmp_path / "docker-compose.yml").read_text(encoding="utf-8")


def test_bootstrap_compose_idempotent_without_force(bootstrap, tmp_path, monkeypatch):
    monkeypatch.setenv("EVILEYE_BOOTSTRAP_TARGET", str(tmp_path))
    monkeypatch.setenv("EVILEYE_BOOTSTRAP_IMAGE", "evileye/app:latest")
    monkeypatch.setenv("POSTGRES_PASSWORD", "pass1")
    assert bootstrap.main([]) == 0

    compose = tmp_path / "docker-compose.yml"
    compose.write_text("# customized\n", encoding="utf-8")
    env = tmp_path / ".env"
    original_env = env.read_text(encoding="utf-8")

    assert bootstrap.main([]) == 0
    assert compose.read_text(encoding="utf-8") == "# customized\n"
    assert env.read_text(encoding="utf-8") == original_env


def test_bootstrap_force_overwrites_compose(bootstrap, tmp_path, monkeypatch):
    monkeypatch.setenv("EVILEYE_BOOTSTRAP_TARGET", str(tmp_path))
    monkeypatch.setenv("EVILEYE_BOOTSTRAP_IMAGE", "evileye/app:cpu")
    monkeypatch.setenv("POSTGRES_PASSWORD", "pass1")
    assert bootstrap.main([]) == 0

    compose = tmp_path / "docker-compose.yml"
    compose.write_text("# customized\n", encoding="utf-8")

    monkeypatch.setenv("EVILEYE_BOOTSTRAP_FORCE", "1")
    assert bootstrap.main(["--force"]) == 0
    assert (tmp_path / "docker-compose.yml.bak").read_text(encoding="utf-8") == "# customized\n"
    text = compose.read_text(encoding="utf-8")
    assert "${EVILEYE_IMAGE:-evileye/app:cpu}" in text
    assert "# customized" not in text


def test_bootstrap_reuses_existing_credentials_password(bootstrap, tmp_path, monkeypatch):
    monkeypatch.setenv("EVILEYE_BOOTSTRAP_TARGET", str(tmp_path))
    monkeypatch.setenv("EVILEYE_BOOTSTRAP_IMAGE", "evileye/app:latest")
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)

    creds = {
        "database": {
            "user_name": "postgres",
            "password": "already-set",
            "admin_password": "already-set",
            "database_name": "evil_eye_db",
            "host_name": "localhost",
            "port": 5432,
        }
    }
    (tmp_path / "credentials.json").write_text(json.dumps(creds), encoding="utf-8")

    assert bootstrap.main([]) == 0
    payload = json.loads((tmp_path / "credentials.json").read_text(encoding="utf-8"))
    assert payload["database"]["password"] == "already-set"
    assert payload["database"]["host_name"] == "db"
    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "POSTGRES_PASSWORD=already-set" in env_text
