"""Browser runtime — structured DOM-first execution with Playwright.

Uses structured selectors and accessibility tree first.
Vision fallback only when page is structurally ambiguous.
"""

import asyncio
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()

BROWSER_PROFILES_DIR = Path("/spool/browser_profiles")


class BrowserRuntime:
    """Manages Playwright browser with persisted profiles."""

    def __init__(self) -> None:
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None

    async def launch(self, profile_name: str | None = None) -> None:
        """Launch browser with optional persisted profile."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.warning("playwright_not_installed", msg="Browser runtime disabled")
            return

        self._playwright = await async_playwright().start()

        launch_args: dict[str, Any] = {"headless": True}
        if profile_name:
            profile_dir = BROWSER_PROFILES_DIR / profile_name
            profile_dir.mkdir(parents=True, exist_ok=True)
            self._browser = await self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                headless=True,
            )
            pages = self._browser.pages
            self._page = pages[0] if pages else await self._browser.new_page()
            self._context = self._browser
        else:
            self._browser = await self._playwright.chromium.launch(**launch_args)
            self._context = await self._browser.new_context()
            self._page = await self._context.new_page()

        logger.info("browser_launched", profile=profile_name)

    async def close(self) -> None:
        """Close browser and cleanup."""
        if self._context:
            await self._context.close()
        if self._browser and not isinstance(self._context, type(self._browser)):
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("browser_closed")

    async def navigate(self, url: str, wait_until: str = "domcontentloaded") -> dict:
        """Navigate to URL and return page state."""
        if not self._page:
            return {"error": "Browser not launched"}
        try:
            await self._page.goto(url, wait_until=wait_until, timeout=30000)
            title = await self._page.title()
            url_final = self._page.url
            return {"title": title, "url": url_final, "success": True}
        except Exception as e:
            logger.error("navigation_failed", url=url, error=str(e))
            return {"error": str(e), "success": False}

    async def search_on_page(
        self,
        query: str,
        input_selector: str = "input[type='search'], input[name='q']",
    ) -> dict:
        """Type a search query using DOM selectors first."""
        if not self._page:
            return {"error": "Browser not launched"}
        try:
            await self._page.wait_for_selector(input_selector, timeout=5000)
            await self._page.fill(input_selector, query)
            await self._page.keyboard.press("Enter")
            await self._page.wait_for_load_state("domcontentloaded")
            return {"success": True, "query": query}
        except Exception as e:
            logger.warning("search_failed", query=query, error=str(e))
            return {"success": False, "error": str(e)}

    async def extract_links(self, selector: str = "a[href]", max_results: int = 20) -> list[dict]:
        """Extract links from current page using DOM."""
        if not self._page:
            return []
        try:
            links = await self._page.eval_on_selector_all(
                selector,
                """els => els.slice(0, arguments[0] || 20).map(el => ({
                    href: el.href,
                    text: el.textContent?.trim() || '',
                    title: el.title || ''
                }))""",
            )
            return links[:max_results]
        except Exception:
            return []

    async def extract_media_info(self) -> dict:
        """Extract media/video information from current page using DOM."""
        if not self._page:
            return {}
        try:
            info = await self._page.evaluate("""() => {
                const sel = 'video, iframe[src*="youtube"], iframe[src*="vimeo"]';
                const videos = document.querySelectorAll(sel);
                const result = {
                    video_count: videos.length,
                    videos: [],
                    title: document.title,
                    meta_description:
                        document.querySelector('meta[name="description"]')?.content || '',
                    og_video: document.querySelector('meta[property="og:video"]')?.content || '',
                    og_duration:
                        document.querySelector('meta[property="video:duration"]')?.content || '',
                };
                videos.forEach(v => {
                    if (v.tagName === 'VIDEO') {
                        result.videos.push({
                            src: v.src || v.querySelector('source')?.src || '',
                            duration: v.duration || null,
                            width: v.videoWidth || null,
                            height: v.videoHeight || null,
                        });
                    } else {
                        result.videos.push({ src: v.src, type: 'iframe' });
                    }
                });
                return result;
            }""")
            return info
        except Exception as e:
            logger.warning("media_extraction_failed", error=str(e))
            return {}

    async def check_playback(self, timeout_sec: int = 10) -> dict:
        """Verify video playback works on current page."""
        if not self._page:
            return {"playback_works": False}
        try:
            video = await self._page.query_selector("video")
            if not video:
                return {"playback_works": False, "reason": "no_video_element"}

            await self._page.evaluate("""() => {
                const v = document.querySelector('video');
                if (v) { v.play().catch(() => {}); }
            }""")
            await asyncio.sleep(min(timeout_sec, 5))

            state = await self._page.evaluate("""() => {
                const v = document.querySelector('video');
                if (!v) return { playing: false };
                return {
                    playing: !v.paused && !v.ended && v.currentTime > 0,
                    currentTime: v.currentTime,
                    duration: v.duration,
                    readyState: v.readyState,
                    width: v.videoWidth,
                    height: v.videoHeight,
                };
            }""")
            return {
                "playback_works": state.get("playing", False),
                "duration_sec": int(state.get("duration", 0)) if state.get("duration") else None,
                "resolution": (
                    f"{state.get('width', 0)}x{state.get('height', 0)}"
                    if state.get("width") else None
                ),
            }
        except Exception as e:
            logger.warning("playback_check_failed", error=str(e))
            return {"playback_works": False, "error": str(e)}

    async def get_page_text(self, max_length: int = 5000) -> str:
        """Get visible text content from current page."""
        if not self._page:
            return ""
        try:
            text = await self._page.evaluate(
                "() => document.body?.innerText?.slice(0, arguments[0] || 5000) || ''"
            )
            return text[:max_length]
        except Exception:
            return ""
