"""Web UI environment check / install helpers for `evileye web`."""
from __future__ import annotations

import importlib
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional


WEB_PYTHON_MODULES: tuple[str, ...] = (
    "fastapi",
    "uvicorn",
    "pydantic",
    "itsdangerous",
)

# pip package name -> import name when they differ
WEB_PIP_PACKAGES: dict[str, str] = {
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
    "pydantic": "pydantic",
    "itsdangerous": "itsdangerous",
    "PyTurboJPEG": "turbojpeg",
}

LIBTURBOJPEG_HINT = (
    "System libjpeg-turbo not found (libturbojpeg.so). "
    "On Debian/Ubuntu: sudo apt install libturbojpeg. "
    "PyTurboJPEG pip package can install without it, but TurboJPEG() needs the native library."
)


@dataclass
class CheckItem:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class WebSetupReport:
    items: list[CheckItem] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Runtime readiness: Python web deps + TurboJPEG native + SPA static."""
        required = {
            "python:fastapi",
            "python:uvicorn",
            "python:pydantic",
            "python:itsdangerous",
            "python:turbojpeg",
            "python:turbojpeg_native",
            "static",
        }
        return all(item.ok for item in self.items if item.name in required)

    def missing_pip_packages(self) -> list[str]:
        by_name = {item.name: item for item in self.items}
        missing: list[str] = []
        for pip_name, mod_name in WEB_PIP_PACKAGES.items():
            item = by_name.get(f"python:{mod_name}")
            if item is not None and not item.ok:
                missing.append(pip_name)
        return missing

    def needs_libturbojpeg(self) -> bool:
        for item in self.items:
            if item.name == "python:turbojpeg_native" and not item.ok:
                # Native check only meaningful when the Python module imported.
                mod = next((i for i in self.items if i.name == "python:turbojpeg"), None)
                if mod is not None and mod.ok:
                    return True
        return False

    def needs_frontend_build(self) -> bool:
        return any(item.name == "static" and not item.ok for item in self.items)

    def needs_node(self) -> bool:
        return any(item.name in {"node", "npm"} and not item.ok for item in self.items)

    def can_serve_ui(self) -> bool:
        """API + SPA can start. Missing native TurboJPEG is allowed (OpenCV preview)."""
        required = {
            "python:fastapi",
            "python:uvicorn",
            "python:pydantic",
            "python:itsdangerous",
            "python:turbojpeg",
            "static",
        }
        by_name = {item.name: item for item in self.items}
        return all(by_name.get(name) is not None and by_name[name].ok for name in required)


@dataclass
class EnsureWebResult:
    ready: bool
    already_ok: bool
    attempted_fix: bool
    opencv_preview: bool
    report: WebSetupReport
    error: str = ""


def _package_root() -> Path:
    return Path(__file__).resolve().parent


def frontend_dir() -> Path:
    return _package_root() / "api" / "frontend"


def static_dir() -> Path:
    return _package_root() / "api" / "static"


def check_python_module(module_name: str) -> CheckItem:
    try:
        importlib.import_module(module_name)
        return CheckItem(name=f"python:{module_name}", ok=True, detail="import ok")
    except Exception as exc:
        return CheckItem(
            name=f"python:{module_name}",
            ok=False,
            detail=f"import failed: {type(exc).__name__}: {exc}",
        )


def check_turbojpeg() -> list[CheckItem]:
    items: list[CheckItem] = []
    try:
        from turbojpeg import TurboJPEG  # type: ignore
    except Exception as exc:
        items.append(
            CheckItem(
                name="python:turbojpeg",
                ok=False,
                detail=f"import failed: {type(exc).__name__}: {exc}",
            )
        )
        items.append(
            CheckItem(
                name="python:turbojpeg_native",
                ok=False,
                detail="skipped (module missing)",
            )
        )
        return items

    items.append(CheckItem(name="python:turbojpeg", ok=True, detail="import ok"))
    try:
        TurboJPEG()
        items.append(
            CheckItem(
                name="python:turbojpeg_native",
                ok=True,
                detail="TurboJPEG() ok",
            )
        )
    except Exception as exc:
        items.append(
            CheckItem(
                name="python:turbojpeg_native",
                ok=False,
                detail=f"{exc}. {LIBTURBOJPEG_HINT}",
            )
        )
    return items


def check_static(path: Optional[Path] = None) -> CheckItem:
    root = path or static_dir()
    index = root / "index.html"
    assets = root / "assets"
    if not index.is_file():
        return CheckItem(name="static", ok=False, detail=f"missing {index}")
    if not assets.is_dir() or not any(assets.iterdir()):
        return CheckItem(name="static", ok=False, detail=f"empty or missing assets in {assets}")
    return CheckItem(name="static", ok=True, detail=str(root))


def check_frontend_sources(path: Optional[Path] = None) -> CheckItem:
    root = path or frontend_dir()
    pkg = root / "package.json"
    if pkg.is_file():
        return CheckItem(name="frontend_sources", ok=True, detail=str(root))
    return CheckItem(name="frontend_sources", ok=False, detail=f"missing {pkg}")


def check_command(name: str) -> CheckItem:
    found = shutil.which(name)
    if found:
        return CheckItem(name=name, ok=True, detail=found)
    return CheckItem(name=name, ok=False, detail=f"{name} not found in PATH")


def collect_web_setup_report(
    *,
    static_path: Optional[Path] = None,
    frontend_path: Optional[Path] = None,
) -> WebSetupReport:
    report = WebSetupReport()
    for mod in WEB_PYTHON_MODULES:
        report.items.append(check_python_module(mod))
    report.items.extend(check_turbojpeg())
    report.items.append(check_command("node"))
    report.items.append(check_command("npm"))
    report.items.append(check_static(static_path))
    report.items.append(check_frontend_sources(frontend_path))
    return report


def pip_install(
    packages: Iterable[str],
    *,
    scope: str = "user",
    python_exe: Optional[str] = None,
    runner: Optional[Callable[..., subprocess.CompletedProcess]] = None,
) -> None:
    pkgs = [p for p in packages if p]
    if not pkgs:
        return
    run = runner or subprocess.run
    exe = python_exe or sys.executable
    cmd = [exe, "-m", "pip", "install"]
    if scope == "user":
        cmd.append("--user")
    elif scope == "system":
        cmd = ["sudo", exe, "-m", "pip", "install"]
    else:
        raise ValueError(f"Unknown scope: {scope}")
    cmd.extend(pkgs)
    result = run(cmd, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        stderr = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"pip install failed ({result.returncode}): {stderr}")


def build_frontend(
    *,
    frontend_path: Optional[Path] = None,
    runner: Optional[Callable[..., subprocess.CompletedProcess]] = None,
) -> None:
    root = frontend_path or frontend_dir()
    if not (root / "package.json").is_file():
        raise FileNotFoundError(f"Frontend sources not found at {root}")
    npm = shutil.which("npm")
    if not npm:
        raise RuntimeError(
            "npm not found. Install Node.js (e.g. sudo apt install nodejs npm) then retry."
        )
    run = runner or subprocess.run
    for args in ([npm, "install"], [npm, "run", "build"]):
        result = run(args, cwd=str(root), check=False, capture_output=True, text=True)
        if result.returncode != 0:
            stderr = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(f"{' '.join(args)} failed ({result.returncode}): {stderr}")


def ensure_web_environment(
    *,
    scope: str = "user",
    force: bool = False,
    build: Optional[bool] = None,
    log: Optional[Callable[[str], None]] = None,
) -> EnsureWebResult:
    """Install missing Python web deps and/or build SPA if the environment is incomplete.

    Native TurboJPEG is optional: preview can fall back to OpenCV.
    """
    scope_norm = (scope or "user").strip().lower()
    if scope_norm not in {"user", "system"}:
        raise ValueError("scope must be 'user' or 'system'")

    report = collect_web_setup_report()
    if report.can_serve_ui() and not force and build is not True:
        return EnsureWebResult(
            ready=True,
            already_ok=True,
            attempted_fix=False,
            opencv_preview=report.needs_libturbojpeg(),
            report=report,
        )

    attempted = False
    try:
        missing = report.missing_pip_packages()
        if missing:
            attempted = True
            if log:
                log(f"Installing Python packages ({scope_norm}): {', '.join(missing)}")
            pip_install(missing, scope=scope_norm)

        report_after_pip = collect_web_setup_report()
        should_build = force or build is True or report.needs_frontend_build() or report_after_pip.needs_frontend_build()
        if build is False:
            should_build = False
        if should_build:
            if report_after_pip.needs_node() or report.needs_node():
                raise RuntimeError(
                    "Node.js/npm required to build the SPA. Install with: sudo apt install nodejs npm"
                )
            attempted = True
            if log:
                log("Building frontend (npm install && npm run build)…")
            build_frontend()
    except Exception as exc:
        final = collect_web_setup_report()
        return EnsureWebResult(
            ready=False,
            already_ok=False,
            attempted_fix=attempted,
            opencv_preview=final.needs_libturbojpeg(),
            report=final,
            error=str(exc),
        )

    final = collect_web_setup_report()
    return EnsureWebResult(
        ready=final.can_serve_ui(),
        already_ok=False,
        attempted_fix=attempted,
        opencv_preview=final.needs_libturbojpeg(),
        report=final,
    )
