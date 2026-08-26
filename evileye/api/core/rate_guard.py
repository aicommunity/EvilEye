"""In-memory sliding-window rate guard with auto IP bans."""
from __future__ import annotations

import ipaddress
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Deque, Optional

from evileye.api.core.client_ip import resolve_client_ip
from evileye.api.core.ip_ban_store import get_ip_ban_store
from evileye.core.logger import get_module_logger

logger = get_module_logger("api.rate_guard")


@dataclass
class ProtectionConfig:
    enabled: bool = True
    trust_proxy: bool = False
    trusted_proxy_ips: list[str] = field(default_factory=lambda: ["127.0.0.1"])
    login_max_failures: int = 10
    login_window_sec: float = 300
    login_ban_sec: float = 1800
    register_max_per_window: int = 5
    register_window_sec: float = 600
    register_ban_sec: float = 3600
    global_max_requests: int = 600
    global_window_sec: float = 60
    global_ban_sec: float = 600
    auth_fail_max: int = 30
    auth_fail_window_sec: float = 60
    auth_fail_ban_sec: float = 900
    ws_connect_max: int = 60
    ws_connect_window_sec: float = 60
    ws_ban_sec: float = 600
    # Soft reconnect window: Live↔Playback remounts should not trip flood ban.
    ws_reconnect_grace_sec: float = 5.0
    # Separate buckets so metadata WS storms do not ban the live grid socket.
    ws_live_max: int = 30
    ws_metadata_max: int = 40
    ws_live_window_sec: float = 60
    ws_metadata_window_sec: float = 60
    internal_fail_max: int = 15
    internal_fail_window_sec: float = 60
    internal_fail_ban_sec: float = 3600
    oversized_max: int = 5
    oversized_window_sec: float = 60
    oversized_ban_sec: float = 3600
    whitelist_ips: list[str] = field(default_factory=lambda: ["127.0.0.1", "::1"])

    def public_snapshot(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "trust_proxy": self.trust_proxy,
            "login_max_failures": self.login_max_failures,
            "login_window_sec": self.login_window_sec,
            "login_ban_sec": self.login_ban_sec,
            "register_max_per_window": self.register_max_per_window,
            "global_max_requests": self.global_max_requests,
            "global_window_sec": self.global_window_sec,
            "whitelist_ips": list(self.whitelist_ips),
        }


def load_protection_config(web_auth_section: dict[str, Any] | None = None) -> ProtectionConfig:
    import os

    section = web_auth_section if isinstance(web_auth_section, dict) else {}
    protection = section.get("protection") if isinstance(section.get("protection"), dict) else {}
    auth_enabled = bool(section.get("enabled", True))
    env_disable = os.getenv("EVILEYE_PROTECTION_ENABLED", "").strip().lower() in {"0", "false", "no"}
    cfg = ProtectionConfig()
    cfg.enabled = (not env_disable) and bool(protection.get("enabled", auth_enabled))
    trust_env = os.getenv("EVILEYE_TRUST_PROXY", "").strip().lower() in {"1", "true", "yes"}
    cfg.trust_proxy = bool(protection.get("trust_proxy", trust_env))
    if isinstance(protection.get("trusted_proxy_ips"), list):
        cfg.trusted_proxy_ips = [str(x) for x in protection["trusted_proxy_ips"]]
    if isinstance(protection.get("whitelist_ips"), list):
        cfg.whitelist_ips = [str(x) for x in protection["whitelist_ips"]]
    for key in (
        "login_max_failures",
        "login_window_sec",
        "login_ban_sec",
        "register_max_per_window",
        "register_window_sec",
        "register_ban_sec",
        "global_max_requests",
        "global_window_sec",
        "global_ban_sec",
        "auth_fail_max",
        "auth_fail_window_sec",
        "auth_fail_ban_sec",
        "ws_connect_max",
        "ws_connect_window_sec",
        "ws_ban_sec",
        "ws_reconnect_grace_sec",
        "ws_live_max",
        "ws_metadata_max",
        "ws_live_window_sec",
        "ws_metadata_window_sec",
        "internal_fail_max",
        "internal_fail_window_sec",
        "internal_fail_ban_sec",
        "oversized_max",
        "oversized_window_sec",
        "oversized_ban_sec",
    ):
        if key in protection:
            try:
                setattr(cfg, key, type(getattr(cfg, key))(protection[key]))
            except (TypeError, ValueError):
                pass
    return cfg


class RateGuard:
    def __init__(self, config: ProtectionConfig | None = None):
        self.config = config or ProtectionConfig()
        self._lock = threading.Lock()
        self._events: dict[tuple[str, str], Deque[float]] = defaultdict(deque)
        self._ws_reject_counts: dict[str, int] = {}

    def configure(self, config: ProtectionConfig) -> None:
        self.config = config

    def client_ip(self, request: Any) -> str:
        return resolve_client_ip(
            request,
            trust_proxy=self.config.trust_proxy,
            trusted_proxy_ips=self.config.trusted_proxy_ips,
        )

    def is_whitelisted(self, ip: str) -> bool:
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return ip in set(self.config.whitelist_ips)
        for entry in self.config.whitelist_ips:
            try:
                if "/" in entry:
                    if addr in ipaddress.ip_network(entry, strict=False):
                        return True
                elif ip == entry:
                    return True
            except ValueError:
                continue
        return False

    def reset_bucket(self, bucket: str, ip: str) -> None:
        with self._lock:
            self._events.pop((bucket, ip), None)

    def _prune(self, q: Deque[float], window: float, now: float) -> None:
        while q and (now - q[0]) > window:
            q.popleft()

    def record(
        self,
        bucket: str,
        ip: str,
        *,
        max_events: int,
        window_sec: float,
        ban_sec: float,
        reason: str,
        auto_ban: bool = True,
    ) -> bool:
        """Return True if threshold exceeded (and ban applied when auto_ban)."""
        if not self.config.enabled or not ip or ip == "unknown":
            return False
        if self.is_whitelisted(ip):
            return False
        now = time.time()
        with self._lock:
            q = self._events[(bucket, ip)]
            self._prune(q, window_sec, now)
            q.append(now)
            exceeded = len(q) >= max_events
        if exceeded and auto_ban:
            get_ip_ban_store().add_ban(
                ip,
                reason=reason,
                source="auto",
                created_by="system",
                duration_sec=ban_sec,
                allow_cidr=False,
                hit_count=max_events,
            )
            self.reset_bucket(bucket, ip)
            return True
        return exceeded

    def record_login_failure(self, request: Any) -> bool:
        ip = self.client_ip(request)
        return self.record(
            "login_fail",
            ip,
            max_events=self.config.login_max_failures,
            window_sec=self.config.login_window_sec,
            ban_sec=self.config.login_ban_sec,
            reason="login_bruteforce",
        )

    def record_login_success(self, request: Any) -> None:
        ip = self.client_ip(request)
        self.reset_bucket("login_fail", ip)

    def record_register(self, request: Any) -> bool:
        ip = self.client_ip(request)
        return self.record(
            "register",
            ip,
            max_events=self.config.register_max_per_window,
            window_sec=self.config.register_window_sec,
            ban_sec=self.config.register_ban_sec,
            reason="register_flood",
        )

    def record_global_request(self, request: Any) -> bool:
        ip = self.client_ip(request)
        return self.record(
            "global",
            ip,
            max_events=self.config.global_max_requests,
            window_sec=self.config.global_window_sec,
            ban_sec=self.config.global_ban_sec,
            reason="http_flood",
        )

    def record_auth_fail_status(self, request: Any) -> bool:
        ip = self.client_ip(request)
        return self.record(
            "auth_fail_status",
            ip,
            max_events=self.config.auth_fail_max,
            window_sec=self.config.auth_fail_window_sec,
            ban_sec=self.config.auth_fail_ban_sec,
            reason="auth_fail_storm",
        )

    def record_ws_connect(self, request: Any, *, bucket: str = "ws_connect") -> bool:
        """Record a WS connect. bucket: ws_live_grid | ws_metadata | ws_connect (legacy)."""
        ip = self.client_ip(request)
        if not self.config.enabled or not ip or ip == "unknown":
            return False
        if self.is_whitelisted(ip):
            return False
        if bucket == "ws_live_grid":
            max_events = int(self.config.ws_live_max)
            window_sec = float(self.config.ws_live_window_sec)
            reason = "ws_live_flood"
        elif bucket == "ws_metadata":
            max_events = int(self.config.ws_metadata_max)
            window_sec = float(self.config.ws_metadata_window_sec)
            reason = "ws_metadata_flood"
        else:
            max_events = int(self.config.ws_connect_max)
            window_sec = float(self.config.ws_connect_window_sec)
            reason = "ws_connect_flood"
            bucket = "ws_connect"
        now = time.time()
        grace = float(self.config.ws_reconnect_grace_sec or 0.0)
        with self._lock:
            q = self._events[(bucket, ip)]
            self._prune(q, window_sec, now)
            # Live↔Playback remount opens sockets in a burst; coalesce within grace.
            if grace > 0 and q and (now - q[-1]) < grace:
                return False
            q.append(now)
            exceeded = len(q) >= max_events
        if exceeded:
            logger.warning(
                "ws_connect_flood bucket=%s ip=%s events=%s window_sec=%s ban_sec=%s",
                bucket,
                ip,
                max_events,
                window_sec,
                self.config.ws_ban_sec,
            )
            get_ip_ban_store().add_ban(
                ip,
                reason=reason,
                source="auto",
                created_by="system",
                duration_sec=self.config.ws_ban_sec,
                allow_cidr=False,
                hit_count=max_events,
            )
            self.reset_bucket(bucket, ip)
            self._bump_ws_reject(reason)
            return True
        return False

    def _bump_ws_reject(self, reason: str) -> None:
        with self._lock:
            self._ws_reject_counts[reason] = int(self._ws_reject_counts.get(reason, 0)) + 1

    def note_ws_reject(self, reason: str) -> None:
        """Count non-flood WS close reasons (banned / permission)."""
        self._bump_ws_reject(reason)

    def ws_reject_counts(self) -> dict[str, int]:
        with self._lock:
            return dict(self._ws_reject_counts)

    def record_internal_fail(self, request: Any) -> bool:
        ip = self.client_ip(request)
        return self.record(
            "internal_fail",
            ip,
            max_events=self.config.internal_fail_max,
            window_sec=self.config.internal_fail_window_sec,
            ban_sec=self.config.internal_fail_ban_sec,
            reason="internal_token_fail",
        )

    def record_oversized_body(self, request: Any) -> bool:
        ip = self.client_ip(request)
        return self.record(
            "oversized",
            ip,
            max_events=self.config.oversized_max,
            window_sec=self.config.oversized_window_sec,
            ban_sec=self.config.oversized_ban_sec,
            reason="oversized_body",
        )


_GUARD: RateGuard | None = None


def get_rate_guard() -> RateGuard:
    global _GUARD
    if _GUARD is None:
        _GUARD = RateGuard()
    return _GUARD


def reset_rate_guard_for_tests(config: ProtectionConfig | None = None) -> RateGuard:
    global _GUARD
    _GUARD = RateGuard(config or ProtectionConfig())
    return _GUARD
