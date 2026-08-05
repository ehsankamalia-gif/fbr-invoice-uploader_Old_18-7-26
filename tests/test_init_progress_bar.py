import os
import sys
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def _read_progress_script() -> str:
    root = Path(__file__).resolve().parents[1]
    p = root / "customer_portal" / "static" / "js" / "init_progress_bar.js"
    return p.read_text(encoding="utf-8")


def _progress_markup() -> str:
    return """
    <div id="init-progress-root" style="position:fixed;top:0;left:0;width:100%;z-index:9999;opacity:1">
      <div style="position:relative;width:100%">
        <div style="width:100%;height:4px;background:#e5e7eb">
          <div id="init-progress-bar" style="height:4px;width:0%"></div>
        </div>
        <div id="init-progress-label" role="status" aria-live="polite">0%</div>
        <div id="init-progress-a11y" role="progressbar" aria-label="Loading" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0">Loading 0%</div>
      </div>
    </div>
    """


def _get_state(page):
    return page.evaluate("window.__initProgress.getState()")


@pytest.mark.parametrize("delay_ms", [800, 1500])
def test_progress_tracks_delayed_fetch(delay_ms):
    script = _read_progress_script()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        html = f"""
        <html>
          <head></head>
          <body>
            {_progress_markup()}
          </body>
        </html>
        """

        page.set_content(html, wait_until="domcontentloaded")

        page.evaluate(
            f"""
            window.fetch = function() {{
              return new Promise((resolve) => {{
                setTimeout(() => resolve(new Response("ok")), {delay_ms});
              }});
            }};
            """
        )

        page.add_script_tag(content=script)
        page.evaluate("(() => { fetch('/api/test'); })()")

        page.wait_for_timeout(150)
        s1 = _get_state(page)
        assert s1["progress"] < 100
        assert s1["fetchInFlight"] >= 1

        page.wait_for_timeout(delay_ms + 1800)
        s2 = _get_state(page)
        assert s2["progress"] == 100
        assert page.evaluate("document.getElementById('init-progress-root').style.display") == "none"
        assert s2["metrics"]["initMs"] < 50

        browser.close()


def test_progress_tracks_large_asset_task():
    script = _read_progress_script()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        html = f"""
        <html>
          <head></head>
          <body>
            {_progress_markup()}
          </body>
        </html>
        """

        page.set_content(html, wait_until="domcontentloaded")
        page.add_script_tag(content=script)
        page.evaluate(
            "(() => { window.__initProgress.registerTask('asset:big', new Promise((r) => setTimeout(r, 1400))); })()"
        )

        page.wait_for_timeout(250)
        s1 = _get_state(page)
        assert s1["progress"] < 100
        assert s1["customTasks"] == 1

        page.wait_for_timeout(2000)
        s2 = _get_state(page)
        assert s2["progress"] == 100
        assert page.evaluate("document.getElementById('init-progress-root').style.display") == "none"

        browser.close()


def test_error_does_not_stick():
    script = _read_progress_script()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        html = f"""
        <html>
          <head></head>
          <body>
            {_progress_markup()}
          </body>
        </html>
        """

        page.set_content(html, wait_until="domcontentloaded")
        page.evaluate(
            """
            window.fetch = function() {
              return new Promise((_, reject) => setTimeout(() => reject(new Error("fail")), 400));
            };
            """
        )
        page.add_script_tag(content=script)
        page.evaluate("(() => { fetch('/api/fail').catch(() => null); })()")

        page.wait_for_timeout(1800)
        s = _get_state(page)
        assert s["progress"] == 100
        assert s["error"] is True
        assert page.evaluate("document.getElementById('init-progress-root').getAttribute('data-state')") == "error"
        assert page.evaluate("document.getElementById('init-progress-root').style.display") == "none"

        browser.close()
