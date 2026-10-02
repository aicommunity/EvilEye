"""Unit tests for controller FPS GUI/headless policy."""

from evileye.controller.fps_policy import (
    apply_controller_fps_policy,
    resolve_effective_controller_fps,
)
from evileye.gui.gui_mode import GUIMode


def test_resolve_headless_uses_fps_headless():
    assert (
        resolve_effective_controller_fps(
            configured_fps=30,
            gui_mode=GUIMode.HEADLESS,
            fps_headless=12,
        )
        == 12.0
    )


def test_resolve_visible_keeps_configured_even_with_fps_headless():
    assert (
        resolve_effective_controller_fps(
            configured_fps=30,
            gui_mode=GUIMode.VISIBLE,
            fps_headless=12,
        )
        == 30.0
    )


def test_resolve_headless_without_fps_headless_keeps_configured():
    assert (
        resolve_effective_controller_fps(
            configured_fps=30,
            gui_mode=GUIMode.HEADLESS,
            fps_headless=None,
        )
        == 30.0
    )


def test_apply_preserves_fps_configured():
    cfg = {"fps": 30, "fps_headless": 12}
    effective = apply_controller_fps_policy(cfg, GUIMode.HEADLESS)
    assert effective == 12.0
    assert cfg["fps"] == 12.0
    assert cfg["fps_configured"] == 30.0
    assert cfg["fps_headless"] == 12

    # Second apply must not treat already-effective fps as configured.
    effective2 = apply_controller_fps_policy(cfg, GUIMode.VISIBLE)
    assert effective2 == 30.0
    assert cfg["fps"] == 30.0
    assert cfg["fps_configured"] == 30.0
