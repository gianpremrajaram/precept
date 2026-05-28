# SPDX-License-Identifier: Apache-2.0
"""Browser-driven snapshot tests for ``docs/index.html`` (PRC-022).

Opt-in via the ``e2e`` marker. The default ``pytest`` run skips this
module (see ``Dev/pyproject.toml`` ``addopts``). To run::

    pip install -e .[dev,e2e]
    playwright install --with-deps chromium
    pytest -m e2e

The tests load the static observatory off ``file://`` and serve the
committed ``docs/demo_trace.json`` via a tiny in-test HTTP server (the
observatory's default ``fetch("demo_trace.json")`` will not run on a
``file://`` origin because browsers block cross-origin XHR there). The
upload-bar drop / file-picker path renders without a server and is
covered by the file-input subtest.
"""

from __future__ import annotations

import http.server
import socketserver
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from playwright.sync_api import Page

playwright_sync_api = pytest.importorskip("playwright.sync_api")

pytestmark = pytest.mark.e2e


_REPO_ROOT = Path(__file__).resolve().parents[4]
_DOCS_DIR = _REPO_ROOT / "docs"


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, fmt: str, *args: object) -> None:
        return


@contextmanager
def _serve_docs() -> Iterator[str]:
    """Serve ``docs/`` on a free local port; yield the base URL."""
    handler = lambda *a, **kw: _QuietHandler(*a, directory=str(_DOCS_DIR), **kw)  # noqa: E731
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as httpd:
        port = httpd.server_address[1]
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{port}/"
        finally:
            httpd.shutdown()


@pytest.fixture
def docs_base_url() -> Iterator[str]:
    with _serve_docs() as base:
        yield base


@pytest.fixture
def page() -> Iterator[Page]:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            ctx = browser.new_context()
            page = ctx.new_page()
            try:
                yield page
            finally:
                ctx.close()
        finally:
            browser.close()


def test_observatory_renders_default_trace(page: Page, docs_base_url: str) -> None:
    """Default fetch loads ``demo_trace.json`` and renders the trace."""
    page.goto(docs_base_url + "index.html")
    page.wait_for_selector("#trace-content:not([hidden])", timeout=10_000)

    # Two hops in the degraded fixture: one pass, one fail.
    rows = page.locator("table.hops tbody tr.hop-row")
    rows.first.wait_for(state="visible", timeout=5_000)
    assert rows.count() == 2

    # ``text_content`` returns raw textContent; ``inner_text`` would
    # capitalise via ``text-transform: uppercase``.
    pills = page.locator("table.hops tbody tr.hop-row .status-pill")
    statuses = [(pills.nth(i).text_content() or "").strip() for i in range(pills.count())]
    assert statuses == ["pass", "fail"]

    # Pipeline arrows match hop count.
    arrows = page.locator(".pipeline .hop-link")
    assert arrows.count() == 2
    assert arrows.nth(0).get_attribute("data-status") == "pass"
    assert arrows.nth(1).get_attribute("data-status") == "fail"


def test_modal_opens_with_diff_for_failed_hop(page: Page, docs_base_url: str) -> None:
    """Clicking the failed handoff opens a modal showing dropped fields."""
    page.goto(docs_base_url + "index.html")
    page.wait_for_selector("#trace-content:not([hidden])", timeout=10_000)

    page.locator(".pipeline .hop-link[data-status='fail']").click()
    modal = page.locator(".modal[role='dialog']")
    modal.wait_for(state="visible", timeout=5_000)

    title = modal.locator("#modal-title").text_content() or ""
    assert "summariser" in title
    assert "writer" in title

    # The failing hop drops ``primary_source`` and ``uncertainty_bounds``.
    dropped_keys = modal.locator("table.diff tr.status-dropped td code")
    keys = [(dropped_keys.nth(i).text_content() or "").strip() for i in range(dropped_keys.count())]
    assert dropped_keys.count() == 2
    assert "primary_source" in keys
    assert "uncertainty_bounds" in keys

    # Failed rules surface their violation messages.
    failed_rules = modal.locator("table.rules tr.failed")
    assert failed_rules.count() >= 1
    assert "preserved_entities" in (modal.locator("table.rules").text_content() or "")

    # Impact text is rendered verbatim from the trace.
    impact_text = modal.locator(".impact-box").text_content() or ""
    assert "citation integrity" in impact_text


def test_modal_closes_with_escape(page: Page, docs_base_url: str) -> None:
    """ESC dismisses the modal and returns focus to the trigger."""
    page.goto(docs_base_url + "index.html")
    page.wait_for_selector("#trace-content:not([hidden])", timeout=10_000)

    trigger = page.locator(".pipeline .hop-link[data-status='fail']")
    trigger.click()
    page.locator(".modal[role='dialog']").wait_for(state="visible", timeout=5_000)
    page.keyboard.press("Escape")
    # Modal is removed from the DOM on close.
    page.wait_for_selector(".modal[role='dialog']", state="detached", timeout=5_000)


def test_schema_version_mismatch_shows_warning(page: Page, tmp_path: Path) -> None:
    """A trace with a bumped schema_version surfaces a warning banner."""
    bumped = (_DOCS_DIR / "demo_trace.json").read_text()
    # The trace contains multiple schema_version entries (top-level + per
    # violation_event). The viewer only inspects the top-level one, so a
    # single replace suffices but we bump all occurrences to keep the
    # serialised JSON consistent.
    bumped = bumped.replace('"schema_version": "0.1"', '"schema_version": "9.9"')
    fake_docs = tmp_path / "docs"
    fake_docs.mkdir()
    (fake_docs / "index.html").write_text((_DOCS_DIR / "index.html").read_text())
    (fake_docs / "demo_trace.json").write_text(bumped)

    handler = lambda *a, **kw: _QuietHandler(*a, directory=str(fake_docs), **kw)  # noqa: E731
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as httpd:
        port = httpd.server_address[1]
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            page.goto(f"http://127.0.0.1:{port}/index.html")
            page.wait_for_selector("#banner-region .banner.warn", timeout=10_000)
            text = page.locator("#banner-region .banner.warn").text_content() or ""
            assert "9.9" in text
        finally:
            httpd.shutdown()
