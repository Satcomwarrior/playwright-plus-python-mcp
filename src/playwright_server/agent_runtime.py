from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
from typing import Any


def _env_path(name: str, default: str) -> Path:
    raw = os.getenv(name, default)
    return Path(raw).expanduser().resolve()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class BrowserSettings:
    profile_dir: Path
    download_dir: Path
    headless: bool
    channel: str | None
    cdp_endpoint: str | None
    viewer_url: str | None
    expected_google_account: str | None

    @classmethod
    def from_env(cls) -> "BrowserSettings":
        return cls(
            profile_dir=_env_path("PW_USER_DATA_DIR", "~/.agent-browser-profile"),
            download_dir=_env_path("PW_DOWNLOAD_DIR", "~/Downloads/agent-browser"),
            headless=_env_bool("PW_HEADLESS", False),
            channel=(os.getenv("PW_BROWSER_CHANNEL") or None),
            cdp_endpoint=(os.getenv("PW_CDP_ENDPOINT") or None),
            viewer_url=(os.getenv("PW_VIEWER_URL") or None),
            expected_google_account=(os.getenv("PW_EXPECTED_GOOGLE_ACCOUNT") or None),
        )

    def ensure_dirs(self) -> None:
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.download_dir.mkdir(parents=True, exist_ok=True)


def account_match(expected: str | None, actual: str | None) -> dict[str, Any]:
    normalized_expected = (expected or "").strip().lower()
    normalized_actual = (actual or "").strip().lower()
    return {
        "match": bool(normalized_expected and normalized_actual and normalized_expected == normalized_actual),
        "expected": expected,
        "actual": actual,
    }


def list_downloads(download_dir: Path, limit: int = 20) -> list[dict[str, Any]]:
    directory = Path(download_dir).expanduser().resolve()
    if not directory.exists():
        return []
    files = [p for p in directory.iterdir() if p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    result: list[dict[str, Any]] = []
    for path in files[: max(0, limit)]:
        stat = path.stat()
        result.append(
            {
                "name": path.name,
                "path": str(path.resolve()),
                "size": stat.st_size,
                "modified": stat.st_mtime,
            }
        )
    return result


def handoff_payload(current_url: str, settings: BrowserSettings, mode: str) -> dict[str, Any]:
    return {
        "mode": mode,
        "current_url": current_url,
        "viewer_url": settings.viewer_url,
        "expected_google_account": settings.expected_google_account,
        "profile_dir": str(settings.profile_dir),
        "download_dir": str(settings.download_dir),
        "instruction": (
            "Use the viewer URL or the visible local browser window for authentication. "
            "Return control to the agent after authentication completes."
        ),
    }


class BrowserSessionManager:
    def __init__(self, settings: BrowserSettings | None = None, playwright_factory=None):
        self.settings = settings or BrowserSettings.from_env()
        self._playwright_factory = playwright_factory
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._mode = None

    async def start(self, url: str | None = None) -> dict[str, Any]:
        if self._page is not None:
            if url:
                await self._page.goto(url)
            return await self.status()

        self.settings.ensure_dirs()
        if self._playwright_factory is None:
            from playwright.async_api import async_playwright
            factory = async_playwright()
        else:
            factory = self._playwright_factory()
        self._playwright = await factory.start()

        if self.settings.cdp_endpoint:
            self._browser = await self._playwright.chromium.connect_over_cdp(self.settings.cdp_endpoint)
            if self._browser.contexts:
                self._context = self._browser.contexts[0]
            else:
                self._context = await self._browser.new_context(accept_downloads=True)
            self._mode = "cdp"
        else:
            kwargs: dict[str, Any] = {
                "user_data_dir": str(self.settings.profile_dir),
                "headless": self.settings.headless,
                "accept_downloads": True,
                "downloads_path": str(self.settings.download_dir),
            }
            if self.settings.channel:
                kwargs["channel"] = self.settings.channel
            self._context = await self._playwright.chromium.launch_persistent_context(**kwargs)
            self._mode = "persistent"

        self._page = self._context.pages[-1] if self._context.pages else await self._context.new_page()
        if url:
            await self._page.goto(url)
        return await self.status()

    async def status(self) -> dict[str, Any]:
        current_url = self._page.url if self._page is not None else ""
        payload = handoff_payload(current_url, self.settings, self._mode or "stopped")
        if self._page is not None:
            try:
                payload["title"] = await self._page.title()
            except Exception:
                payload["title"] = ""
        else:
            payload["title"] = ""
        return payload

    async def navigate(self, url: str) -> dict[str, Any]:
        await self.start()
        await self._page.goto(url)
        return await self.status()

    async def visible_text(self, limit: int = 20000) -> str:
        await self.start()
        text = await self._page.locator("body").inner_text()
        return text[:limit]

    async def screenshot(self, full_page: bool = True) -> bytes:
        await self.start()
        return await self._page.screenshot(full_page=full_page)

    async def click(self, selector: str) -> dict[str, Any]:
        await self.start()
        await self._page.locator(selector).click()
        return await self.status()

    async def click_text(self, text: str) -> dict[str, Any]:
        await self.start()
        await self._page.get_by_text(text, exact=False).first.click()
        return await self.status()

    async def fill(self, selector: str, value: str) -> dict[str, Any]:
        await self.start()
        await self._page.locator(selector).fill(value)
        return await self.status()

    async def click_and_download(
        self,
        *,
        selector: str | None = None,
        text: str | None = None,
        timeout_ms: int = 30000,
    ) -> dict[str, Any]:
        if not selector and not text:
            raise ValueError("selector or text is required")
        await self.start()
        if selector:
            locator = self._page.locator(selector)
        else:
            locator = self._page.get_by_text(text, exact=False).first

        async with self._page.expect_download(timeout=timeout_ms) as info:
            await locator.click()
        download = await info.value
        target = self.settings.download_dir / download.suggested_filename
        await download.save_as(str(target))
        return {
            "name": target.name,
            "path": str(target.resolve()),
            "size": target.stat().st_size if target.exists() else None,
            "source_url": getattr(download, "url", None),
        }

    async def close(self) -> None:
        if self._mode == "persistent" and self._context is not None:
            await self._context.close()
        elif self._browser is not None:
            await self._browser.close()
        if self._playwright is not None:
            await self._playwright.stop()
        self._browser = None
        self._context = None
        self._page = None
        self._playwright = None
        self._mode = None
