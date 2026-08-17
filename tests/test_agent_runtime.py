from pathlib import Path
import os
import time

import pytest

from playwright_server.agent_runtime import (
    BrowserSettings,
    BrowserSessionManager,
    account_match,
    handoff_payload,
    list_downloads,
)


def test_settings_use_persistent_profile_and_download_dir(tmp_path, monkeypatch):
    profile = tmp_path / "profile"
    downloads = tmp_path / "downloads"
    monkeypatch.setenv("PW_USER_DATA_DIR", str(profile))
    monkeypatch.setenv("PW_DOWNLOAD_DIR", str(downloads))
    monkeypatch.setenv("PW_HEADLESS", "false")
    monkeypatch.setenv("PW_VIEWER_URL", "https://viewer.example/session/abc")
    monkeypatch.setenv("PW_EXPECTED_GOOGLE_ACCOUNT", "satcomwarrior@gmail.com")

    settings = BrowserSettings.from_env()

    assert settings.profile_dir == profile
    assert settings.download_dir == downloads
    assert settings.headless is False
    assert settings.viewer_url == "https://viewer.example/session/abc"
    assert settings.expected_google_account == "satcomwarrior@gmail.com"


def test_account_match_is_case_insensitive_and_reports_mismatch():
    assert account_match("satcomwarrior@gmail.com", "SatcomWarrior@gmail.com")["match"] is True
    assert account_match("satcomwarrior@gmail.com", "3desertrats@gmail.com") == {
        "match": False,
        "expected": "satcomwarrior@gmail.com",
        "actual": "3desertrats@gmail.com",
    }


def test_list_downloads_returns_newest_first(tmp_path):
    old = tmp_path / "old.pdf"
    new = tmp_path / "new.pdf"
    old.write_bytes(b"old")
    new.write_bytes(b"newer")
    now = time.time()
    os.utime(old, (now - 20, now - 20))
    os.utime(new, (now, now))

    result = list_downloads(tmp_path)

    assert [item["name"] for item in result] == ["new.pdf", "old.pdf"]
    assert result[0]["size"] == 5
    assert Path(result[0]["path"]).is_absolute()


def test_handoff_payload_exposes_viewer_url_without_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("PW_USER_DATA_DIR", str(tmp_path / "profile"))
    monkeypatch.setenv("PW_DOWNLOAD_DIR", str(tmp_path / "downloads"))
    monkeypatch.setenv("PW_VIEWER_URL", "https://viewer.example/session/abc")
    monkeypatch.setenv("PW_EXPECTED_GOOGLE_ACCOUNT", "satcomwarrior@gmail.com")
    settings = BrowserSettings.from_env()

    payload = handoff_payload("https://mail.google.com/mail/u/0/#inbox", settings, mode="persistent")

    assert payload["viewer_url"] == "https://viewer.example/session/abc"
    assert payload["current_url"].startswith("https://mail.google.com/")
    assert payload["expected_google_account"] == "satcomwarrior@gmail.com"
    assert "password" not in str(payload).lower()
    assert "cookie" not in str(payload).lower()


class _FakePage:
    def __init__(self):
        self.url = "about:blank"
        self.visited = []

    async def goto(self, url):
        self.url = url
        self.visited.append(url)

    async def title(self):
        return "Fake Title"


class _FakeContext:
    def __init__(self):
        self.pages = [_FakePage()]

    async def new_page(self):
        page = _FakePage()
        self.pages.append(page)
        return page

    async def close(self):
        pass


class _FakeBrowser:
    def __init__(self, context):
        self.contexts = [context]

    async def close(self):
        pass


class _FakeChromium:
    def __init__(self):
        self.persistent_kwargs = None
        self.cdp_endpoint = None
        self.context = _FakeContext()

    async def launch_persistent_context(self, **kwargs):
        self.persistent_kwargs = kwargs
        return self.context

    async def connect_over_cdp(self, endpoint):
        self.cdp_endpoint = endpoint
        return _FakeBrowser(self.context)


class _FakePlaywright:
    def __init__(self):
        self.chromium = _FakeChromium()

    async def stop(self):
        pass


class _FakeFactory:
    def __init__(self, pw):
        self.pw = pw

    async def start(self):
        return self.pw


@pytest.mark.asyncio
async def test_browser_manager_uses_persistent_profile_and_downloads(tmp_path):
    settings = BrowserSettings(
        profile_dir=tmp_path / "profile",
        download_dir=tmp_path / "downloads",
        headless=False,
        channel=None,
        cdp_endpoint=None,
        viewer_url=None,
        expected_google_account="satcomwarrior@gmail.com",
    )
    pw = _FakePlaywright()
    manager = BrowserSessionManager(settings, playwright_factory=lambda: _FakeFactory(pw))

    status = await manager.start("https://mail.google.com/")

    kwargs = pw.chromium.persistent_kwargs
    assert Path(kwargs["user_data_dir"]) == settings.profile_dir
    assert kwargs["accept_downloads"] is True
    assert Path(kwargs["downloads_path"]) == settings.download_dir
    assert status["mode"] == "persistent"
    assert status["current_url"] == "https://mail.google.com/"


@pytest.mark.asyncio
async def test_browser_manager_can_attach_to_existing_chrome_over_cdp(tmp_path):
    settings = BrowserSettings(
        profile_dir=tmp_path / "profile",
        download_dir=tmp_path / "downloads",
        headless=False,
        channel=None,
        cdp_endpoint="http://127.0.0.1:9222",
        viewer_url="http://viewer",
        expected_google_account="satcomwarrior@gmail.com",
    )
    pw = _FakePlaywright()
    manager = BrowserSessionManager(settings, playwright_factory=lambda: _FakeFactory(pw))

    status = await manager.start()

    assert pw.chromium.cdp_endpoint == "http://127.0.0.1:9222"
    assert status["mode"] == "cdp"
    assert status["viewer_url"] == "http://viewer"
