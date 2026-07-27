"""
Browser handler module — manages Selenium WebDriver lifecycle
and provides methods for interacting with Google Drive viewer.
"""

import os
import sys
import shutil
import time
import base64
import json
from typing import Optional, List, Tuple

from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, 
    NoSuchElementException,
    WebDriverException
)
try:
    from selenium_stealth import stealth as _apply_stealth
    _HAS_STEALTH = True
except ImportError:
    _HAS_STEALTH = False

import config
from utils import log_info, log_warning, log_error, log_success, log_progress


class BrowserHandler:
    """Manages Chrome browser for Google Drive file access."""

    def __init__(self):
        self.driver: Optional[webdriver.Chrome] = None
        self._total_pages: int = 0
    
    @staticmethod
    def _find_chrome_binary() -> str:
        """Locate Chrome/Chromium binary. Auto-detects on Linux (Streamlit Cloud / Docker)."""
        if config.CHROME_USER_DATA_DIR:
            return ""  # user profile set — let the driver find it itself
        if not sys.platform.startswith("linux"):
            return ""
        for name in ("chromium-browser", "chromium", "google-chrome", "google-chrome-stable"):
            path = shutil.which(name)
            if path:
                log_info(f"Auto-detected Chrome binary: {path}")
                return path
        return ""

    @staticmethod
    def _build_service() -> ChromeService:
        """
        Build a ChromeService.
        - On Linux: use system chromedriver (installed via packages.txt on Streamlit Cloud).
        - Elsewhere: use webdriver_manager to auto-download a matching driver.
        """
        if sys.platform.startswith("linux"):
            driver_path = shutil.which("chromedriver")
            if driver_path:
                log_info(f"Using system chromedriver: {driver_path}")
                return ChromeService(executable_path=driver_path)
            log_warning("chromedriver not found in PATH on Linux, falling back to webdriver_manager")
        # Windows / Mac / Linux fallback
        from webdriver_manager.chrome import ChromeDriverManager
        return ChromeService(ChromeDriverManager().install())

    def start(self) -> webdriver.Chrome:
        """Initialize and return a configured Chrome WebDriver with stealth patches."""
        log_info("Initializing Chrome browser...")

        options = ChromeOptions()

        if config.HEADLESS:
            options.add_argument("--headless=new")

        options.add_argument(f"--window-size={config.BROWSER_WIDTH},{config.BROWSER_HEIGHT}")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-setuid-sandbox")
        options.add_argument("--remote-debugging-port=0")
        # Suppress automation flags detected by Google
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        if config.CHROME_USER_DATA_DIR:
            options.add_argument(f"--user-data-dir={config.CHROME_USER_DATA_DIR}")
            options.add_argument(f"--profile-directory={config.CHROME_PROFILE}")
            log_info(f"Using Chrome profile: {config.CHROME_PROFILE}")

        chrome_bin = self._find_chrome_binary()
        if chrome_bin:
            options.binary_location = chrome_bin

        try:
            service = self._build_service()
            self.driver = webdriver.Chrome(service=service, options=options)

            # Apply selenium-stealth anti-bot patches (replaces undetected_chromedriver)
            if _HAS_STEALTH:
                _apply_stealth(
                    self.driver,
                    languages=["en-US", "en"],
                    vendor="Google Inc.",
                    platform="Win32",
                    webgl_vendor="Intel Inc.",
                    renderer="Intel Iris OpenGL Engine",
                    fix_hairline=True,
                )
                log_info("selenium-stealth applied")
            else:
                log_warning("selenium-stealth not installed — bot detection may trigger")

            if config.DEVICE_SCALE_FACTOR > 1:
                self.driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", {
                    "width": config.BROWSER_WIDTH,
                    "height": config.BROWSER_HEIGHT,
                    "deviceScaleFactor": config.DEVICE_SCALE_FACTOR,
                    "mobile": False,
                })

            log_success("Chrome browser initialized successfully")
            return self.driver

        except WebDriverException as e:
            log_error(f"Failed to start Chrome: {e}")
            raise RuntimeError(
                "Could not start Chrome browser. Make sure:\n"
                "  1. Google Chrome / Chromium is installed\n"
                "  2. Chrome version is compatible\n"
                "  3. On Streamlit Cloud: packages.txt must contain 'chromium' and 'chromium-driver'"
            )
    
    def open_file(self, url: str) -> bool:
        """Navigate to a Google Drive file URL and wait for it to load."""
        if not self.driver:
            raise RuntimeError("Browser not started. Call start() first.")
        
        log_info("Opening file URL...")
        self.driver.get(url)
        time.sleep(config.PAGE_LOAD_WAIT)
        
        if self._check_for_errors():
            return False
        return True
    
    def get_folder_file_ids(self, folder_url: str) -> List[Tuple[str, str]]:
        """Extract file IDs and their names from a Google Drive folder."""
        if not self.driver:
            raise RuntimeError("Browser not started. Call start() first.")
            
        log_info("Opening folder URL...")
        self.driver.get(folder_url)
        time.sleep(config.PAGE_LOAD_WAIT + 2) # Give it extra time
        
        if self._check_for_errors():
            return []
            
        # Try to scroll the virtual list to load all items
        log_info("Scanning folder for files...")
        self.driver.execute_script("""
            let scrollers = document.querySelectorAll('div[role="main"], div[role="grid"], c-wiz[role="main"]');
            for (let s of scrollers) {
                if (s.scrollHeight > s.clientHeight) {
                    s.scrollTop = s.scrollHeight;
                }
            }
        """)
        time.sleep(2)
        
        # Extract files: items with data-id
        results = self.driver.execute_script("""
            // Only select items that are actual rows/grid cells to avoid picking up the folder header
            let items = document.querySelectorAll('div[data-id][role="row"], div[data-id][role="gridcell"], div[data-id][role="option"], c-wiz[data-id]');
            if (items.length === 0) {
                // Fallback if roles are missing
                items = document.querySelectorAll('div[data-id]');
            }
            
            let files = [];
            let seen = new Set();
            for (let item of items) {
                let id = item.getAttribute('data-id');
                // Skip invalid or folder IDs
                if (!id || id.length < 15 || seen.has(id)) continue;
                
                // Exclude obvious folders by checking text or aria-labels
                let text = (item.textContent || '').toLowerCase();
                let aria = (item.getAttribute('aria-label') || '').toLowerCase();
                
                // If it's a folder or the header, skip
                if (aria.includes('folder ') || aria.includes('thư mục ') || text.includes('thư mục') || aria.includes('owner') || item.tagName === 'C-WIZ') {
                    // Check if it's really just the folder container
                    if (!item.querySelector('[aria-label*="."]')) {
                       continue;
                    }
                }
                
                // Try to get title
                let title = "";
                let titleEl = item.querySelector('[aria-label]');
                if (titleEl) {
                    title = titleEl.getAttribute('aria-label');
                    // Clean up title (Google Drive adds things like "Image, filename.png")
                    if (title.includes(', ')) {
                        title = title.split(', ').slice(1).join(', ');
                    }
                } else {
                    title = item.innerText.split('\\n')[0];
                }
                
                // If the title still looks like a folder name and doesn't have an extension, we might want to skip it, 
                // but we will keep it for now as some files don't have extensions.
                if (title) {
                   files.push([id, title || 'untitled']);
                   seen.add(id);
                }
            }
            return files;
        """)
        
        return results or []
    
    def get_file_title(self) -> str:
        """Extract the file title from the Google Drive viewer page."""
        false_positives = {
            "mở bằng", "open with", "google drive", "drive", 
            "xem trước", "preview", "tải xuống", "download",
            "chia sẻ", "share", "in", "print"
        }
        
        def _ok(t):
            return t and t.strip() and len(t.strip()) > 2 and t.strip().lower() not in false_positives
        
        try:
            page_title = self.driver.title or ""
            if " - Google Drive" in page_title:
                c = page_title.replace(" - Google Drive", "").strip()
                if _ok(c):
                    return c
            
            for sel in ["div.ndfHFb-c4YZDc-Wrber-LgbsSe-haAclf",
                         "div.ndfHFb-c4YZDc-cYAaBc-DARUcf-Df1ZY-bN97Pc"]:
                try:
                    el = self.driver.find_element(By.CSS_SELECTOR, sel)
                    t = el.text or el.get_attribute("data-tooltip") or ""
                    if _ok(t):
                        return t.strip()
                except NoSuchElementException:
                    continue
            
            if page_title and _ok(page_title):
                return page_title.strip()
            return "untitled"
        except Exception:
            return "untitled"
    
    def get_total_pages(self) -> int:
        """Detect the total number of pages from the toolbar indicator."""
        try:
            total = self.driver.execute_script("""
            // Method 1: aria-label on input like "Trang 1/47" or "Page 1 of 47"
            let inputs = document.querySelectorAll('input');
            for (let inp of inputs) {
                let label = inp.getAttribute('aria-label') || '';
                let m = label.match(/\\/\\s*(\\d+)/) || label.match(/of\\s+(\\d+)/i);
                if (m) return parseInt(m[1]);
                let p = inp.parentElement;
                if (p) {
                    let t = p.textContent || '';
                    let m2 = t.match(/\\/\\s*(\\d+)/) || t.match(/of\\s+(\\d+)/i);
                    if (m2) return parseInt(m2[1]);
                }
            }
            // Method 2: thumbnail sidebar items
            let thumbs = document.querySelectorAll('[id^="shDDDe"]');
            if (thumbs.length > 0) return thumbs.length;
            // Method 3: page containers  
            let pages = document.querySelectorAll('[role="img"][aria-label*="Page"], [role="img"][aria-label*="Trang"]');
            if (pages.length > 0) return pages.length;
            return 0;
            """)
            return int(total) if total else 0
        except Exception as e:
            log_warning(f"Could not detect page count: {e}")
            return 0
    
    def scroll_through_all_pages(self, total_pages: int = 0, progress_callback=None) -> int:
        """
        Scroll through entire document using Python-controlled loop.
        This ensures all lazy-loaded pages are rendered.
        """
        self._total_pages = total_pages
        log_info("Scrolling through document to load all pages...")
        if progress_callback:
            progress_callback(0, total_pages or 1, "Scrolling document to load pages...")
        if total_pages > 0:
            log_info(f"Target: {total_pages} pages")
        
        # Step 1: Find the scrollable container
        found = self.driver.execute_script("""
        let best = null, bestH = 0;
        for (let d of document.querySelectorAll('div')) {
            let s = window.getComputedStyle(d);
            let ov = s.overflow + s.overflowY;
            let scrollable = ov.includes('auto') || ov.includes('scroll');
            if (scrollable && d.scrollHeight > d.clientHeight + 50 
                && d.clientHeight > 200 && d.scrollHeight > bestH) {
                best = d; bestH = d.scrollHeight;
            }
        }
        if (!best) {
            for (let d of document.querySelectorAll('div')) {
                if (d.scrollHeight > d.clientHeight + 200 
                    && d.clientHeight > 300 && d.scrollHeight > bestH) {
                    best = d; bestH = d.scrollHeight;
                }
            }
        }
        if (best) {
            window.__sc = best;
            return [bestH, best.clientHeight];
        }
        return null;
        """)
        
        if not found:
            log_warning("No scroll container found, using keyboard fallback")
            self._keyboard_scroll(total_pages)
            return self.get_total_pages() or total_pages or 1
        
        scroll_height, client_height = found
        scroll_step = max(client_height * 0.7, 300)
        log_info(f"Container: height={scroll_height}px, viewport={client_height}px")
        
        # Step 2: Scroll incrementally, tracking blob count
        current_pos = 0
        max_passes = 3
        
        for pass_num in range(1, max_passes + 1):
            if pass_num > 1:
                log_info(f"Pass {pass_num}: re-scrolling to load remaining pages...")
                current_pos = 0
                self.driver.execute_script("if(window.__sc) window.__sc.scrollTop=0;")
                time.sleep(1)
            
            stale = 0
            last_blobs = 0
            
            while True:
                current_pos += scroll_step
                result = self.driver.execute_script("""
                if (!window.__sc) return [0, 0];
                window.__sc.scrollTop = arguments[0];
                return [
                    window.__sc.scrollHeight,
                    document.querySelectorAll('img[src^="blob:"]').length
                ];
                """, current_pos)
                
                new_h, blobs = result if result else (scroll_height, 0)
                scroll_height = max(scroll_height, new_h)
                
                if total_pages > 0:
                    log_progress(min(blobs, total_pages), total_pages, f"  Pass {pass_num}:")
                    if progress_callback:
                        progress_callback(min(blobs, total_pages), total_pages, f"Loading page {min(blobs, total_pages)}/{total_pages}")
                
                # All pages loaded?
                if total_pages > 0 and blobs >= total_pages:
                    break
                
                # Reached bottom?
                if current_pos >= scroll_height:
                    time.sleep(config.SCROLL_WAIT)
                    # Check if scroll height grew
                    new_h2 = self.driver.execute_script(
                        "return window.__sc ? window.__sc.scrollHeight : 0;"
                    )
                    if new_h2 and new_h2 > scroll_height:
                        scroll_height = new_h2
                    else:
                        break
                
                # Stale detection
                if blobs == last_blobs:
                    stale += 1
                    if stale >= 8 and current_pos >= scroll_height:
                        break
                else:
                    stale = 0
                    last_blobs = blobs
                
                time.sleep(config.SCROLL_WAIT)
            
            time.sleep(config.FINAL_WAIT)
            
            final_blobs = self.driver.execute_script(
                "return document.querySelectorAll('img[src^=\"blob:\"]').length;"
            ) or 0
            
            log_info(f"After pass {pass_num}: {final_blobs} blob images loaded")
            
            if total_pages <= 0 or final_blobs >= total_pages:
                break
        
        # Scroll back to top
        self.driver.execute_script("if(window.__sc) window.__sc.scrollTop=0;")
        time.sleep(1)
        
        detected = self.get_total_pages()
        return max(detected, final_blobs, total_pages)
    
    def _keyboard_scroll(self, total_pages: int = 0):
        """Fallback: scroll using Page Down key."""
        body = self.driver.find_element(By.TAG_NAME, "body")
        iters = max((total_pages or 20) * 3, 60)
        for i in range(iters):
            body.send_keys(Keys.PAGE_DOWN)
            time.sleep(config.SCROLL_WAIT)
            if total_pages > 0 and i % 5 == 0:
                blobs = self.driver.execute_script(
                    "return document.querySelectorAll('img[src^=\"blob:\"]').length||0;"
                ) or 0
                log_progress(min(blobs, total_pages), total_pages, "  Loading:")
                if blobs >= total_pages:
                    break
        body.send_keys(Keys.HOME)
        time.sleep(1)
    
    def capture_page_images(self, total_pages: int = 0, progress_callback=None) -> List[bytes]:
        """
        Extract all page images from the Google Drive viewer.
        Uses page-by-page scrolling to handle lazy-loaded content.
        """
        total_pages = total_pages or self._total_pages
        
        # Try bulk extraction first
        if progress_callback:
            progress_callback(0, total_pages or 1, "Extracting loaded images...")
        images = self._extract_all_blobs()
        if images and (total_pages <= 0 or len(images) >= total_pages):
            log_success(f"Extracted {len(images)} pages in bulk")
            return images
        
        got = len(images) if images else 0
        if total_pages > 0 and got < total_pages:
            log_warning(f"Bulk extraction got {got}/{total_pages}. Trying page-by-page...")
            images = self._extract_page_by_page(total_pages, progress_callback)
            if images and len(images) >= total_pages * 0.9:
                log_success(f"Extracted {len(images)} pages via page-by-page")
                return images
        
        # Fallback strategies
        if not images:
            images = self._extract_rendered_images()
        if not images:
            log_info("Using screenshot fallback...")
            images = self._capture_via_screenshots()
        
        if images:
            return images
        
        log_error("Could not extract any page images")
        return []
    
    def _extract_all_blobs(self) -> List[bytes]:
        """Extract all currently loaded blob images at once."""
        try:
            results = self.driver.execute_script("""
            let imgs = document.querySelectorAll('img[src^="blob:"]');
            let out = [];
            for (let img of imgs) {
                if (img.naturalWidth < 200 || img.naturalHeight < 200) continue;
                try {
                    let c = document.createElement('canvas');
                    c.width = img.naturalWidth;
                    c.height = img.naturalHeight;
                    c.getContext('2d').drawImage(img, 0, 0);
                    out.push(c.toDataURL('image/png'));
                } catch(e) {}
            }
            return out;
            """)
            if not results:
                return []
            return [base64.b64decode(d.split(',',1)[1]) for d in results if d and ',' in d]
        except Exception as e:
            log_warning(f"Bulk blob extraction failed: {e}")
            return []
    
    def _extract_page_by_page(self, total_pages: int, progress_callback=None) -> List[bytes]:
        """
        Scroll to each page individually, wait for it to render,
        then extract its blob image. This handles lazy-loading properly.
        """
        images = []
        
        # Scroll back to top first
        self.driver.execute_script("if(window.__sc) window.__sc.scrollTop=0;")
        time.sleep(1)
        
        # Get container info
        info = self.driver.execute_script("""
        if (!window.__sc) return null;
        return {
            sh: window.__sc.scrollHeight,
            ch: window.__sc.clientHeight
        };
        """)
        
        if not info:
            return []
        
        page_height = info['sh'] / total_pages
        
        for page_idx in range(total_pages):
            # Scroll to position this page in view
            scroll_pos = page_idx * page_height
            self.driver.execute_script(
                "if(window.__sc) window.__sc.scrollTop = arguments[0];",
                scroll_pos
            )
            time.sleep(config.SCROLL_WAIT * 1.2)
            
            # Extract the blob image that is currently in the viewport area
            img_data = self.driver.execute_script("""
            let targetY = arguments[0];
            let container = window.__sc;
            if (!container) return null;
            
            // Find the blob image closest to the current scroll position
            let imgs = document.querySelectorAll('img[src^="blob:"]');
            let best = null;
            let bestDist = Infinity;
            
            for (let img of imgs) {
                if (img.naturalWidth < 200 || img.naturalHeight < 200) continue;
                let rect = img.getBoundingClientRect();
                let imgCenter = rect.top + rect.height / 2;
                let viewCenter = window.innerHeight / 2;
                let dist = Math.abs(imgCenter - viewCenter);
                if (dist < bestDist) {
                    bestDist = dist;
                    best = img;
                }
            }
            
            if (!best) return null;
            
            try {
                let c = document.createElement('canvas');
                c.width = best.naturalWidth;
                c.height = best.naturalHeight;
                c.getContext('2d').drawImage(best, 0, 0);
                return c.toDataURL('image/png');
            } catch(e) { return null; }
            """, scroll_pos)
            
            if img_data and ',' in img_data:
                img_bytes = base64.b64decode(img_data.split(',', 1)[1])
                # Deduplicate: check if this image is the same as the last one
                if not images or img_bytes != images[-1]:
                    images.append(img_bytes)
            
            log_progress(page_idx + 1, total_pages, "  Extracting:")
            if progress_callback:
                progress_callback(page_idx + 1, total_pages, f"Extracting high-quality image {page_idx + 1}/{total_pages}")
        
        return images
    
    def _extract_rendered_images(self) -> List[bytes]:
        """Extract rendered page images from the document viewer."""
        try:
            data_urls = self.driver.execute_script("""
            let results = [];
            let containers = document.querySelectorAll(
                '[role="img"][aria-label*="Page"], [role="img"][aria-label*="Trang"], '
                + '.drive-viewer-paginated-page, .ndfHFb-c4YZDc-Wrber-SM8H3c-V1ur5d'
            );
            if (containers.length === 0) {
                let allImgs = document.querySelectorAll('img');
                for (let img of allImgs) {
                    if (img.naturalWidth > 400 && img.naturalHeight > 400) {
                        try {
                            let c = document.createElement('canvas');
                            c.width = img.naturalWidth; c.height = img.naturalHeight;
                            c.getContext('2d').drawImage(img, 0, 0);
                            results.push(c.toDataURL('image/png'));
                        } catch(e) {}
                    }
                }
            } else {
                for (let ct of containers) {
                    let img = ct.querySelector('img');
                    if (img && img.naturalWidth > 200) {
                        try {
                            let c = document.createElement('canvas');
                            c.width = img.naturalWidth; c.height = img.naturalHeight;
                            c.getContext('2d').drawImage(img, 0, 0);
                            results.push(c.toDataURL('image/png'));
                        } catch(e) {}
                    }
                }
            }
            return results;
            """)
            if not data_urls:
                return []
            return [base64.b64decode(d.split(',',1)[1]) for d in data_urls if d and ',' in d]
        except Exception as e:
            log_warning(f"Rendered image extraction failed: {e}")
            return []
    
    def _capture_via_screenshots(self) -> List[bytes]:
        """Capture pages via screenshots as a last resort."""
        try:
            page_count = self.driver.execute_script(
                "return document.querySelectorAll('img[src^=\"blob:\"]').length;"
            ) or 0
            if page_count > 0:
                return self._screenshot_individual_pages(page_count)
            screenshot = self.driver.get_screenshot_as_png()
            return [screenshot] if screenshot else []
        except Exception as e:
            log_error(f"Screenshot capture failed: {e}")
            return []
    
    def _screenshot_individual_pages(self, page_count: int) -> List[bytes]:
        """Take individual screenshots of each page element."""
        images = []
        for i in range(page_count):
            try:
                self.driver.execute_script("""
                let imgs = document.querySelectorAll('img[src^="blob:"]');
                if (arguments[0] < imgs.length) {
                    imgs[arguments[0]].scrollIntoView({behavior:'instant',block:'start'});
                }
                """, i)
                time.sleep(config.SCROLL_WAIT)
                screenshot = self.driver.get_screenshot_as_png()
                if screenshot:
                    images.append(screenshot)
                    log_progress(i + 1, page_count, "  Capturing:")
            except Exception as e:
                log_warning(f"Failed to capture page {i + 1}: {e}")
        return images
    
    def _check_for_errors(self) -> bool:
        """Check if the page shows an error."""
        try:
            page_title = (self.driver.title or "").lower()
            for err in ["error", "not found", "denied", "403", "404"]:
                if err in page_title and "google drive" not in page_title:
                    log_error(f"Page title indicates error: {self.driver.title}")
                    return True
            
            for sel in ["[data-error-code]", ".uc-error-caption"]:
                try:
                    el = self.driver.find_element(By.CSS_SELECTOR, sel)
                    if el and el.is_displayed():
                        log_error(f"Error element: {el.text}")
                        return True
                except NoSuchElementException:
                    continue
            
            try:
                body = self.driver.find_element(By.TAG_NAME, "body").text.lower()
                for phrase in ["you need access", "request access",
                               "sorry, the file you have requested does not exist",
                               "you need permission"]:
                    if phrase in body:
                        log_error(f"Access error: {phrase}")
                        return True
            except Exception:
                pass
            return False
        except Exception:
            return False
    
    def close(self):
        """Close the browser and clean up."""
        if self.driver:
            try:
                self.driver.quit()
                log_info("Browser closed")
            except Exception:
                pass
            self.driver = None
