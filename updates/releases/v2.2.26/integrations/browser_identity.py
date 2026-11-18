"""SHADOW Browser Identity V2 - On-Demand Dynamic Config Provider.

Location: integrations/browser_identity.py

Purpose:
    * Create temporary, independent Playwright BrowserContexts on demand.
    * Apply stable, rotated test-environment settings (viewport, locale, timezone) per session.
    * Report browser environment and non-sensitive diagnostics safely.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import threading
from typing import Any, Optional
import uuid

__all__ = [
    "IdentityConfig", "IdentityReport", "BrowserIdentitySession",
    "BrowserIdentityManager", "BrowserIdentityError",
]


class BrowserIdentityError(RuntimeError):
    """Raised when a session is misused or its lifecycle is invalid."""


@dataclass(frozen=True)
class IdentityConfig:
    """Dynamic and stable environment choices for anti-detection compatibility testing."""

    config_id: str
    slot_id: int
    viewport_width: int
    viewport_height: int
    locale: str
    timezone_id: str
    color_scheme: str
    block_service_workers: bool = False
    allow_downloads: bool = False

    def playwright_options(self) -> dict[str, Any]:
        return {
            "viewport": {"width": self.viewport_width, "height": self.viewport_height},
            "accept_downloads": self.allow_downloads,
            "permissions": [],
            "ignore_https_errors": False,
            "service_workers": "block" if self.block_service_workers else "allow",
            "locale": self.locale,
            "timezone_id": self.timezone_id,
            "color_scheme": self.color_scheme,
        }


@dataclass(frozen=True)
class IdentityReport:
    session_label: str
    config_id: str
    slot_id: int
    captured_utc: str
    config: dict[str, Any]
    environment: dict[str, Any]
    graphics: dict[str, Any]
    storage: dict[str, Any]

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=indent)


_READ_ONLY_DIAGNOSTICS = r"""() => {
  const safe = (fn, fallback = null) => { try { return fn(); } catch (_) { return fallback; } };
  const canvas = safe(() => document.createElement('canvas'));
  const gl = safe(() => canvas.getContext('webgl2') || canvas.getContext('webgl'));
  const mq = (query) => safe(() => matchMedia(query).matches, false);
  const storeCount = (storeName) => safe(() => window[storeName].length);
  return {
    environment: {
      browser_user_agent: safe(() => navigator.userAgent),
      platform: safe(() => navigator.platform),
      language: safe(() => navigator.language),
      languages: safe(() => Array.from(navigator.languages || [])),
      timezone: safe(() => Intl.DateTimeFormat().resolvedOptions().timeZone),
      viewport: { width: innerWidth, height: innerHeight },
    },
    graphics: {
      webgl_supported: Boolean(gl),
    },
    storage: {
      indexed_db_available: safe(() => Boolean(window.indexedDB))
    }
  };
}"""


class BrowserIdentitySession:
    def __init__(self, context: Any, label: str, config: IdentityConfig):
        self.context = context
        self.label = label
        self.config = config
        self._thread_id = threading.get_ident()
        self._closed = False

    @property
    def is_closed(self) -> bool:
        return self._closed

    def _assert_ready(self) -> None:
        if threading.get_ident() != self._thread_id:
            raise BrowserIdentityError("Use session only on browser-owning thread")
        if self._closed:
            raise BrowserIdentityError("Session is already closed")

    def new_page(self) -> Any:
        self._assert_ready()
        return self.context.new_page()

    def diagnostics(self, page: Any) -> IdentityReport:
        self._assert_ready()
        data = page.evaluate(_READ_ONLY_DIAGNOSTICS)
        if not isinstance(data, dict):
            data = {}
        storage = {"cookie_count": len(self.context.cookies()), "persistent_profile": False}
        return IdentityReport(
            session_label=self.label,
            config_id=self.config.config_id,
            slot_id=self.config.slot_id,
            captured_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            config=asdict(self.config),
            environment=dict(data.get("environment") or {}),
            graphics=dict(data.get("graphics") or {}),
            storage=storage,
        )

    def close(self) -> None:
        if self._closed:
            return
        self._assert_ready()
        try:
            self.context.close()
        finally:
            self._closed = True

    def __enter__(self) -> "BrowserIdentitySession":
        return self

    def __exit__(self, _type: Any, _value: Any, _tb: Any) -> None:
        self.close()


class BrowserIdentityManager:
    """Dynamic configuration provider that rotates pool presets per request."""

    VIEWPORTS = [
        {"width": 1920, "height": 1080},
        {"width": 1366, "height": 768},
        {"width": 1536, "height": 864},
        {"width": 1440, "height": 900},
        {"width": 1280, "height": 800},
    ]
    LOCALES = ["en-US", "en-GB", "fr-FR", "es-ES", "de-DE"]
    TIMEZONES = ["America/New_York", "Europe/London", "Europe/Paris", "Europe/Madrid"]
    SCHEMES = ["light", "dark", "no-preference"]

    def __init__(self):
        self._active_configs = {}

    def request_config(self, slot_id: int, session_request_id: Optional[str] = None) -> IdentityConfig:
        """إنشاء إعدادات جديدة وفريدة (On-Demand Configuration) لكل جلسة فحص جديدة"""
        vp = random.choice(self.VIEWPORTS)
        config_id = f"cfg_{uuid.uuid4().hex[:12]}"
        
        config = IdentityConfig(
            config_id=config_id,
            slot_id=slot_id,
            viewport_width=vp["width"],
            viewport_height=vp["height"],
            locale=random.choice(self.LOCALES),
            timezone_id=random.choice(self.TIMEZONES),
            color_scheme=random.choice(self.SCHEMES),
        )
        self._active_configs[config_id] = config
        return config

    def create(self, browser: Any, slot_id: int, label: str = "Browser") -> BrowserIdentitySession:
        config = self.request_config(slot_id)
        context = browser.new_context(**config.playwright_options())
        return BrowserIdentitySession(context, label.strip(), config)

    def release_config(self, config_id: str) -> None:
        self._active_configs.pop(config_id, None)


def _demo() -> None:
    from playwright.sync_api import sync_playwright
    manager = BrowserIdentityManager()
    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        try:
            with manager.create(browser, slot_id=1, label="Demo Slot #1") as session:
                page = session.new_page()
                page.goto("about:blank")
                print(session.diagnostics(page).to_json())
        finally:
            browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="SHADOW Browser Identity V2")
    parser.add_argument("--demo", action="store_true", help="run demo")
    args = parser.parse_args()
    if args.demo:
        _demo()


if __name__ == "__main__":
    main()