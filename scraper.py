"""
Website Scraper module — auto-detects and extracts content from any website.
Uses Selenium for rendering + BeautifulSoup for parsing.
"""

import os
import sys
import time
import base64
import hashlib
from dataclasses import dataclass, field
from typing import Optional, List, Dict
from urllib.parse import urljoin, urlparse

from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from PIL import Image
import io

import config
from utils import log_info, log_warning, log_error, log_success


@dataclass
class ScrapedItem:
    """Represents a single piece of scraped content."""
    title: str = ""
    url: str = ""
    text: str = ""
    images: List[bytes] = field(default_factory=list)
    metadata: Dict[str, str] = field(default_factory=dict)
    section: str = "general"


@dataclass
class ScrapedPage:
    """Represents the full result of scraping one page."""
    source_url: str = ""
    page_title: str = ""
    page_description: str = ""
    page_favicon: str = ""
    canonical_url: str = ""
    items: List[ScrapedItem] = field(default_factory=list)
    main_content: str = ""
    all_images: List[bytes] = field(default_factory=list)
    scrape_time: str = ""
    stats: Dict[str, int] = field(default_factory=dict)


class ScraperBrowser:
    """Manages Chrome browser for scraping — shares config with BrowserHandler."""

    def __init__(self):
        self.driver: Optional[webdriver.Chrome] = None

    @staticmethod
    def _build_service() -> ChromeService:
        if sys.platform.startswith("linux"):
            import shutil
            driver_path = shutil.which("chromedriver")
            if driver_path:
                return ChromeService(executable_path=driver_path)
        from webdriver_manager.chrome import ChromeDriverManager
        return ChromeService(ChromeDriverManager().install())

    def start(self):
        options = ChromeOptions()
        if config.HEADLESS:
            options.add_argument("--headless=new")
        options.add_argument(f"--window-size={config.BROWSER_WIDTH},{config.BROWSER_HEIGHT}")
        options.add_argument("--use-gl=swiftshader")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        options.add_argument("--enable-features=NetworkService,NetworkServiceInProcess")

        try:
            service = self._build_service()
            self.driver = webdriver.Chrome(service=service, options=options)
            return self.driver
        except Exception as e:
            raise RuntimeError(f"Could not start Chrome: {e}")

    def close(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None


class AutoContentDetector:
    """Auto-detects main content, articles, lists, tables, images from a page."""

    # Common selectors for main content areas
    MAIN_CONTENT_SELECTORS = [
        "article",
        "main",
        '[role="main"]',
        ".post-content",
        ".entry-content",
        ".article-body",
        ".content",
        "#content",
        ".main-content",
        ".post",
        ".article",
        ".story-body",
        ".article__body",
        ".field--name-body",
        ".td-post-content",
        ".entry",
        ".single-post",
    ]

    # Selectors for article/list items
    ITEM_SELECTORS = [
        "article",
        ".post",
        ".entry",
        ".card",
        ".item",
        ".news-item",
        ".article-card",
        ".product-item",
        ".list-item",
        ".blog-post",
        "section",
    ]

    # Noise elements to remove
    NOISE_SELECTORS = [
        "nav", "header", "footer", "aside",
        ".sidebar", ".navigation", ".menu", ".nav",
        ".ads", ".advertisement", ".ad-container",
        ".cookie-banner", ".cookie-notice",
        ".social-share", ".share-buttons",
        ".comments", ".comment-section",
        ".newsletter", ".subscribe",
        "script", "style", "noscript",
        ".popup", ".modal", ".overlay",
        ".breadcrumb", ".pagination",
    ]

    @staticmethod
    def detect_main_content(soup: BeautifulSoup) -> Optional[str]:
        """Extract the main content block from a page."""
        for selector in AutoContentDetector.MAIN_CONTENT_SELECTORS:
            elements = soup.select(selector)
            for el in elements:
                text = el.get_text(strip=True)
                if len(text) > 100:
                    return AutoContentDetector._clean_element(el)
        return None

    @staticmethod
    def detect_items(soup: BeautifulSoup, source_url: str) -> List[ScrapedItem]:
        """Detect individual content items (articles, posts, products, etc.)."""
        items = []
        seen_titles = set()

        for selector in AutoContentDetector.ITEM_SELECTORS:
            elements = soup.select(selector)
            if len(elements) < 1:
                continue

            for el in elements:
                item = AutoContentDetector._parse_item(el, source_url)
                if item and item.title and item.title not in seen_titles:
                    seen_titles.add(item.title)
                    items.append(item)

            if items:
                break

        return items

    @staticmethod
    def _parse_item(el, source_url: str) -> Optional[ScrapedItem]:
        """Parse a single content item element."""
        title_el = el.find(["h1", "h2", "h3", "h4", "a"], class_=lambda c: c and any(
            kw in str(c).lower() for kw in ["title", "heading", "headline", "name"]
        ))
        if not title_el:
            title_el = el.find(["h2", "h3", "a"])
        if not title_el:
            return None

        title = title_el.get_text(strip=True)
        if len(title) < 3:
            return None

        link = title_el.get("href", "")
        if link and not link.startswith(("http", "mailto:")):
            link = urljoin(source_url, link)

        text_parts = []
        for p in el.find_all(["p", "span", "div"], class_=lambda c: c and any(
            kw in str(c).lower() for kw in ["excerpt", "summary", "description", "content", "text"]
        )):
            t = p.get_text(strip=True)
            if len(t) > 20:
                text_parts.append(t)

        if not text_parts:
            for p in el.find_all("p"):
                t = p.get_text(strip=True)
                if len(t) > 20:
                    text_parts.append(t)

        return ScrapedItem(
            title=title,
            url=link,
            text="\n\n".join(text_parts[:5]),
            section="item",
        )

    @staticmethod
    def extract_images(soup: BeautifulSoup, source_url: str, browser=None) -> List[bytes]:
        """Extract meaningful images from the page."""
        images = []
        seen_hashes = set()

        img_tags = soup.find_all("img")
        for img in img_tags:
            src = img.get("src") or img.get("data-src") or img.get("data-lazy-src") or ""
            if not src:
                continue

            if src.startswith("//"):
                src = "https:" + src
            elif not src.startswith(("http", "data:")):
                src = urljoin(source_url, src)

            if src.startswith("data:"):
                try:
                    img_bytes = base64.b64decode(src.split(",", 1)[1])
                    img_hash = hashlib.md5(img_bytes).hexdigest()
                    if img_hash not in seen_hashes and len(img_bytes) > 2000:
                        seen_hashes.add(img_hash)
                        images.append(img_bytes)
                except Exception:
                    pass
            elif browser and browser.driver:
                try:
                    img_bytes = AutoContentDetector._fetch_image_via_browser(browser.driver, src)
                    if img_bytes:
                        img_hash = hashlib.md5(img_bytes).hexdigest()
                        if img_hash not in seen_hashes:
                            seen_hashes.add(img_hash)
                            images.append(img_bytes)
                except Exception:
                    pass

        return images[:20]

    @staticmethod
    def _fetch_image_via_browser(driver, url: str) -> Optional[bytes]:
        """Fetch an image via browser and return as bytes."""
        try:
            result = driver.execute_async_script("""
                var url = arguments[0];
                var callback = arguments[1];
                fetch(url)
                    .then(r => r.blob())
                    .then(blob => {
                        var reader = new FileReader();
                        reader.onloadend = () => callback(reader.result);
                        reader.readAsDataURL(blob);
                    })
                    .catch(() => callback(null));
            """, url)
            if result and isinstance(result, str) and "," in result:
                return base64.b64decode(result.split(",", 1)[1])
        except Exception:
            pass
        return None

    @staticmethod
    def _clean_element(el) -> str:
        """Clean an element: remove noise, return clean HTML/text."""
        clone = BeautifulSoup(str(el), "html.parser")
        for selector in AutoContentDetector.NOISE_SELECTORS:
            for noise in clone.select(selector):
                noise.decompose()
        text = clone.get_text("\n", strip=True)
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        return "\n".join(lines)

    @staticmethod
    def extract_metadata(soup: BeautifulSoup) -> Dict[str, str]:
        """Extract page metadata from meta tags."""
        meta = {}

        title_tag = soup.find("title")
        if title_tag:
            meta["title"] = title_tag.get_text(strip=True)

        for tag in soup.find_all("meta"):
            name = tag.get("name") or tag.get("property") or ""
            content = tag.get("content") or ""
            if name and content:
                key = name.lower().replace("og:", "").replace("twitter:", "")
                if key in ("title", "description", "image", "site_name", "author", "date", "published_time"):
                    meta[key] = content

        canonical = soup.find("link", rel="canonical")
        if canonical:
            meta["canonical"] = canonical.get("href", "")

        return meta


class WebsiteScraper:
    """Main scraper class — orchestrates browser, detection, and extraction."""

    def __init__(self):
        self.browser = ScraperBrowser()

    def scrape(self, url: str, progress_callback=None) -> Optional[ScrapedPage]:
        """
        Scrape a website and return structured data.

        Args:
            url: Target website URL
            progress_callback: Optional callback(current, total, message)

        Returns:
            ScrapedPage with extracted content, or None on failure
        """
        if progress_callback:
            progress_callback(0, 100, "Đang khởi động trình duyệt...")

        try:
            self.browser.start()

            if progress_callback:
                progress_callback(10, 100, f"Đang mở {url}...")

            self.browser.driver.get(url)
            time.sleep(config.PAGE_LOAD_WAIT)

            if progress_callback:
                progress_callback(30, 100, "Đang chờ trang tải hoàn tất...")

            self._wait_for_content(timeout=30)

            if progress_callback:
                progress_callback(50, 100, "Đang phân tích nội dung trang...")

            html = self.browser.driver.page_source
            soup = BeautifulSoup(html, "html.parser")

            result = ScrapedPage(source_url=url)

            meta = AutoContentDetector.extract_metadata(soup)
            result.page_title = meta.get("title", self.browser.driver.title or "")
            result.page_description = meta.get("description", "")
            result.canonical_url = meta.get("canonical", url)
            result.scrape_time = time.strftime("%Y-%m-%d %H:%M:%S")

            if progress_callback:
                progress_callback(60, 100, "Đang trích xuất nội dung chính...")

            main_content = AutoContentDetector.detect_main_content(soup)
            if main_content:
                result.main_content = main_content

            if progress_callback:
                progress_callback(70, 100, "Đang phát hiện các mục nội dung...")

            items = AutoContentDetector.detect_items(soup, url)
            result.items = items

            if progress_callback:
                progress_callback(85, 100, "Đang trích xuất hình ảnh...")

            images = AutoContentDetector.extract_images(soup, url, self.browser)
            result.all_images = images

            result.stats = {
                "total_items": len(items),
                "total_images": len(images),
                "content_length": len(main_content) if main_content else 0,
            }

            if progress_callback:
                progress_callback(100, 100, "Hoàn tất scraping!")

            return result

        except Exception as e:
            log_error(f"Scraping failed: {e}")
            return None
        finally:
            self.browser.close()

    def _wait_for_content(self, timeout: int = 30) -> bool:
        """Wait until page has meaningful content."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            result = self.browser.driver.execute_script("""
                var text = document.body ? document.body.innerText : '';
                var imgs = document.querySelectorAll('img').length;
                var articles = document.querySelectorAll('article, .content, .post, .entry, main').length;
                return text.length + imgs * 50 + articles * 100;
            """) or 0
            if result > 200:
                return True
            time.sleep(0.5)
        return True
