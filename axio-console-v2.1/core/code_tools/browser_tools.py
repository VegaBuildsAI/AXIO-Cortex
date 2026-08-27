"""Optional headless Playwright browser tools with SSRF and action boundaries."""

from __future__ import annotations

import atexit
import json
import re

from core.config import AXIO_BROWSER_TIMEOUT, AXIO_WEB_MAX_CHARS

from .network_policy import UnsafeUrlError, route_url_is_allowed, validate_public_url
from .registry import CodeTool, ToolResult


class BrowserRuntime:
    def __init__(self) -> None:
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    def ensure(self):
        if self.page is not None:
            return self.page
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Playwright is not installed. Run .\\.venv\\Scripts\\python.exe -m pip install playwright "
                "and then .\\.venv\\Scripts\\python.exe -m playwright install chromium"
            ) from exc
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=True)
        self.context = self.browser.new_context(
            accept_downloads=False,
            service_workers="block",
            viewport={"width": 1440, "height": 1000},
        )
        self.context.set_default_timeout(AXIO_BROWSER_TIMEOUT * 1000)
        self.context.set_default_navigation_timeout(AXIO_BROWSER_TIMEOUT * 1000)

        def guard(route) -> None:
            if route_url_is_allowed(route.request.url):
                route.continue_()
            else:
                route.abort("blockedbyclient")

        self.context.route("**/*", guard)
        self.page = self.context.new_page()
        return self.page

    def close(self) -> None:
        for item in (self.context, self.browser):
            if item is not None:
                try:
                    item.close()
                except Exception:
                    pass
        if self.playwright is not None:
            try:
                self.playwright.stop()
            except Exception:
                pass
        self.playwright = self.browser = self.context = self.page = None


_RUNTIME = BrowserRuntime()
atexit.register(_RUNTIME.close)


def browser_open(url: str) -> ToolResult:
    try:
        target = validate_public_url(url)
        page = _RUNTIME.ensure()
        response = page.goto(target, wait_until="domcontentloaded", timeout=AXIO_BROWSER_TIMEOUT * 1000)
        final_url = validate_public_url(page.url)
        return ToolResult(json.dumps({
            "url": final_url,
            "title": page.title(),
            "status": response.status if response is not None else None,
        }, ensure_ascii=False, indent=2))
    except Exception as exc:
        return ToolResult(f"ERROR: browser_open failed: {exc}", ok=False)


def _snapshot_data(max_chars: int = AXIO_WEB_MAX_CHARS) -> dict:
    page = _RUNTIME.ensure()
    if not page.url or page.url == "about:blank":
        raise ValueError("No page is open. Call browser_open first.")
    limit = max(1_000, min(int(max_chars), AXIO_WEB_MAX_CHARS))
    elements = page.evaluate(
        """() => {
          const nodes = Array.from(document.querySelectorAll('a,button,input,select,textarea'));
          return nodes.slice(0, 120).map((el, i) => {
            const ref = `axio-${i + 1}`;
            el.setAttribute('data-axio-ref', ref);
            return {
              ref,
              tag: el.tagName.toLowerCase(),
              type: (el.getAttribute('type') || '').toLowerCase(),
              text: (el.innerText || el.getAttribute('aria-label') || el.getAttribute('name') || '').trim().slice(0, 240),
              href: el.href || null,
              disabled: !!el.disabled,
              in_form: !!el.closest('form')
            };
          });
        }"""
    )
    text = page.locator("body").inner_text(timeout=AXIO_BROWSER_TIMEOUT * 1000)
    return {
        "url": validate_public_url(page.url),
        "title": page.title(),
        "truncated": len(text) > limit,
        "text": text[:limit],
        "interactive": elements,
    }


def browser_snapshot(max_chars: int = AXIO_WEB_MAX_CHARS) -> ToolResult:
    try:
        return ToolResult(json.dumps(_snapshot_data(max_chars), ensure_ascii=False, indent=2))
    except Exception as exc:
        return ToolResult(f"ERROR: browser_snapshot failed: {exc}", ok=False)


def browser_click(ref: str) -> ToolResult:
    if not re.fullmatch(r"axio-[1-9][0-9]{0,2}", str(ref)):
        return ToolResult("ERROR: browser_click requires a ref returned by browser_snapshot", ok=False)
    try:
        page = _RUNTIME.ensure()
        locator = page.locator(f'[data-axio-ref="{ref}"]')
        if locator.count() != 1:
            return ToolResult(f"ERROR: Browser ref is stale or ambiguous: {ref}. Take a new snapshot.", ok=False)
        metadata = locator.evaluate(
            "el => ({tag: el.tagName.toLowerCase(), type: (el.type || '').toLowerCase(), in_form: !!el.closest('form'), href: el.href || null})"
        )
        if metadata["tag"] not in {"a", "button"}:
            return ToolResult("ERROR: Only links and non-submit buttons can be clicked", ok=False)
        if metadata["in_form"] or metadata["type"] == "submit":
            return ToolResult("ERROR: Form submission is blocked; no form-submit tool is enabled", ok=False)
        if metadata.get("href"):
            validate_public_url(metadata["href"])
        locator.click(timeout=AXIO_BROWSER_TIMEOUT * 1000)
        page.wait_for_timeout(300)
        if page.url and page.url != "about:blank":
            validate_public_url(page.url)
        snapshot = _snapshot_data(min(8_000, AXIO_WEB_MAX_CHARS))
        return ToolResult(json.dumps({"clicked": ref, "page": snapshot}, ensure_ascii=False, indent=2))
    except (UnsafeUrlError, Exception) as exc:
        return ToolResult(f"ERROR: browser_click failed: {exc}", ok=False)


TOOLS = [
    CodeTool("browser_open", "Open a public URL in a persistent headless Chromium page; blocks localhost, private networks, file URLs, downloads, and service workers.", {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}, browser_open, "read"),
    CodeTool("browser_snapshot", "Return bounded rendered page text and stable refs for visible interactive elements.", {"type": "object", "properties": {"max_chars": {"type": "integer", "minimum": 1000}}, "required": []}, browser_snapshot, "read"),
    CodeTool("browser_click", "Click one link or non-submit button by a ref from browser_snapshot. Form submission, upload, and download remain blocked. Requires approval.", {"type": "object", "properties": {"ref": {"type": "string"}}, "required": ["ref"]}, browser_click, "execute"),
]
