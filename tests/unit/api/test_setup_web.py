"""Tests for evileye.setup_web helpers and CLI check exit codes."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from evileye import setup_web as sw
from evileye.cli import app


runner = CliRunner()


def test_check_static_ok(tmp_path: Path) -> None:
    static = tmp_path / "static"
    assets = static / "assets"
    assets.mkdir(parents=True)
    (static / "index.html").write_text("<html></html>", encoding="utf-8")
    (assets / "app.js").write_text("console.log(1)", encoding="utf-8")
    item = sw.check_static(static)
    assert item.ok


def test_check_static_missing(tmp_path: Path) -> None:
    item = sw.check_static(tmp_path / "missing")
    assert not item.ok


def test_missing_pip_packages_detects_failed_imports() -> None:
    report = sw.WebSetupReport(
        items=[
            sw.CheckItem("python:fastapi", False, "import failed"),
            sw.CheckItem("python:uvicorn", True, "ok"),
            sw.CheckItem("python:pydantic", True, "ok"),
            sw.CheckItem("python:itsdangerous", True, "ok"),
            sw.CheckItem("python:turbojpeg", False, "import failed"),
        ]
    )
    missing = report.missing_pip_packages()
    assert "fastapi" in missing
    assert "PyTurboJPEG" in missing
    assert "uvicorn" not in missing


def test_report_ok_requires_static_and_turbojpeg_native() -> None:
    report = sw.WebSetupReport(
        items=[
            sw.CheckItem("python:fastapi", True),
            sw.CheckItem("python:uvicorn", True),
            sw.CheckItem("python:pydantic", True),
            sw.CheckItem("python:itsdangerous", True),
            sw.CheckItem("python:turbojpeg", True),
            sw.CheckItem("python:turbojpeg_native", False, "no lib"),
            sw.CheckItem("static", True),
            sw.CheckItem("node", False),
        ]
    )
    assert not report.ok
    assert report.needs_libturbojpeg()
    assert report.can_serve_ui()


def test_ensure_web_environment_skips_when_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    ready = sw.WebSetupReport(
        items=[
            sw.CheckItem("python:fastapi", True),
            sw.CheckItem("python:uvicorn", True),
            sw.CheckItem("python:pydantic", True),
            sw.CheckItem("python:itsdangerous", True),
            sw.CheckItem("python:turbojpeg", True),
            sw.CheckItem("python:turbojpeg_native", True),
            sw.CheckItem("static", True),
        ]
    )
    monkeypatch.setattr(sw, "collect_web_setup_report", lambda **kwargs: ready)

    def _fail_pip(*args, **kwargs):
        raise AssertionError("pip should not run")

    monkeypatch.setattr(sw, "pip_install", _fail_pip)
    result = sw.ensure_web_environment()
    assert result.ready
    assert result.already_ok
    assert not result.attempted_fix


def test_ensure_web_for_server_skips_when_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    from evileye.cli import _ensure_web_environment_for_server

    ready = sw.WebSetupReport(
        items=[
            sw.CheckItem("python:fastapi", True),
            sw.CheckItem("python:uvicorn", True),
            sw.CheckItem("python:pydantic", True),
            sw.CheckItem("python:itsdangerous", True),
            sw.CheckItem("python:turbojpeg", True),
            sw.CheckItem("python:turbojpeg_native", True),
            sw.CheckItem("static", True),
        ]
    )
    monkeypatch.setattr(sw, "collect_web_setup_report", lambda **kwargs: ready)
    called = {"n": 0}

    def _should_not_run(**kwargs):
        called["n"] += 1
        raise AssertionError("ensure_web_environment should not run")

    monkeypatch.setattr(sw, "ensure_web_environment", _should_not_run)
    _ensure_web_environment_for_server()
    assert called["n"] == 0


def test_ensure_web_for_server_exits_when_fix_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    import typer
    from evileye.cli import _ensure_web_environment_for_server

    broken = sw.WebSetupReport(
        items=[
            sw.CheckItem("python:fastapi", False, "missing"),
            sw.CheckItem("python:uvicorn", True),
            sw.CheckItem("python:pydantic", True),
            sw.CheckItem("python:itsdangerous", True),
            sw.CheckItem("python:turbojpeg", True),
            sw.CheckItem("python:turbojpeg_native", True),
            sw.CheckItem("static", True),
        ]
    )
    monkeypatch.setattr(sw, "collect_web_setup_report", lambda **kwargs: broken)
    monkeypatch.setattr(
        sw,
        "ensure_web_environment",
        lambda **kwargs: sw.EnsureWebResult(
            ready=False,
            already_ok=False,
            attempted_fix=True,
            opencv_preview=False,
            report=broken,
            error="pip failed",
        ),
    )
    with pytest.raises(typer.Exit) as exc:
        _ensure_web_environment_for_server()
    assert exc.value.exit_code == 1


def test_pip_install_user_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd, check=False, capture_output=True, text=True):
        calls.append(list(cmd))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    sw.pip_install(["fastapi"], scope="user", python_exe="/usr/bin/python3", runner=fake_run)
    assert calls
    assert calls[0][:4] == ["/usr/bin/python3", "-m", "pip", "install"]
    assert "--user" in calls[0]
    assert "fastapi" in calls[0]


def test_pip_install_system_scope_uses_sudo(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd, check=False, capture_output=True, text=True):
        calls.append(list(cmd))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    sw.pip_install(["uvicorn"], scope="system", python_exe="/usr/bin/python3", runner=fake_run)
    assert calls[0][0] == "sudo"
    assert "--user" not in calls[0]


def test_setup_web_check_exit_code(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    static = tmp_path / "static"
    assets = static / "assets"
    assets.mkdir(parents=True)
    (static / "index.html").write_text("ok", encoding="utf-8")
    (assets / "a.js").write_text("1", encoding="utf-8")
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text("{}", encoding="utf-8")

    def fake_report(**kwargs):
        return sw.WebSetupReport(
            items=[
                sw.CheckItem("python:fastapi", True),
                sw.CheckItem("python:uvicorn", True),
                sw.CheckItem("python:pydantic", True),
                sw.CheckItem("python:itsdangerous", True),
                sw.CheckItem("python:turbojpeg", True),
                sw.CheckItem("python:turbojpeg_native", True),
                sw.CheckItem("node", True, "/usr/bin/node"),
                sw.CheckItem("npm", True, "/usr/bin/npm"),
                sw.CheckItem("static", True, str(static)),
                sw.CheckItem("frontend_sources", True, str(frontend)),
            ]
        )

    monkeypatch.setattr(sw, "collect_web_setup_report", fake_report)
    result = runner.invoke(app, ["setup-web", "--check"])
    assert result.exit_code == 0


def test_setup_web_check_fails_without_static(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_report(**kwargs):
        return sw.WebSetupReport(
            items=[
                sw.CheckItem("python:fastapi", True),
                sw.CheckItem("python:uvicorn", True),
                sw.CheckItem("python:pydantic", True),
                sw.CheckItem("python:itsdangerous", True),
                sw.CheckItem("python:turbojpeg", True),
                sw.CheckItem("python:turbojpeg_native", True),
                sw.CheckItem("node", True),
                sw.CheckItem("npm", True),
                sw.CheckItem("static", False, "missing"),
                sw.CheckItem("frontend_sources", True),
            ]
        )

    monkeypatch.setattr(sw, "collect_web_setup_report", fake_report)
    result = runner.invoke(app, ["setup-web", "--check"])
    assert result.exit_code == 1
