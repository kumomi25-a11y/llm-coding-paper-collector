"""PDF downloader for academic papers.

Multi-strategy:
1. Direct OA HTTP download
2. Unpaywall API for alternative OA copies
3. ResearchGate search
4. EZProxy direct PDF URLs (via HTTP with stored cookies)
5. Playwright for SSO login (visible browser), then HTTP with extracted cookies
"""

import json
import logging
import time
import re
from pathlib import Path
from urllib.parse import urljoin

import requests

logger = logging.getLogger("paper_collector")


class EZProxyDownloader:
    def __init__(
        self,
        ezproxy_base: str = "https://lib.ezproxy.ust.hk/login?url=",
        user_data_dir: str = "./auth/playwright_profile",
        open_access_first: bool = True,
        timeout: int = 60,
        headless: bool = True,
        email: str = None,
    ):
        self.ezproxy_base = ezproxy_base
        self.user_data_dir = str(Path(user_data_dir).absolute())
        self.open_access_first = open_access_first
        self.timeout = timeout
        self.headless = headless
        self.email = email
        self._playwright = None
        self._context = None
        self._browser = None
        self._cookies = None  # Extracted EZProxy cookies for HTTP download

        # HTTP session
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": "application/pdf,text/html,*/*",
            "Accept-Language": "en-US,en;q=0.9",
        })

    # ── Playwright lifecycle (only for SSO login) ──

    def start(self):
        from playwright.sync_api import sync_playwright
        self._playwright = sync_playwright().start()
        Path(self.user_data_dir).mkdir(parents=True, exist_ok=True)

        try:
            self._context = self._playwright.chromium.launch_persistent_context(
                self.user_data_dir,
                headless=self.headless,
                viewport={"width": 1280, "height": 800},
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                ),
                args=["--disable-blink-features=AutomationControlled"],
            )
        except Exception:
            self._browser = self._playwright.chromium.launch(
                headless=self.headless,
                args=["--disable-blink-features=AutomationControlled"],
            )
            self._context = self._browser.new_context()

        # Load saved cookies into HTTP session
        self._load_cookies()

    def stop(self):
        if self._context:
            self._context.close()
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()

    def _load_cookies(self):
        """Extract cookies from Playwright context into requests session."""
        if not self._context:
            return
        try:
            pw_cookies = self._context.cookies()
            cookie_dict = {}
            for c in pw_cookies:
                cookie_dict[c["name"]] = c["value"]
            # Set as Cookie header for EZProxy domain
            if cookie_dict:
                self.session.cookies.clear()
                for name, value in cookie_dict.items():
                    self.session.cookies.set(name, value, domain=".hkust.edu.hk")
                self._cookies = cookie_dict
                logger.info(f"Loaded {len(cookie_dict)} cookies from Playwright session")
        except Exception as e:
            logger.debug(f"Cookie extraction failed: {e}")

    def ezproxy_login(self, test_doi: str = "10.1111/puar.70098") -> bool:
        """Open visible browser for EZProxy SSO login. Returns True if successful."""
        if not self._context:
            self.start()

        page = self._context.new_page()
        test_url = f"{self.ezproxy_base}https://onlinelibrary.wiley.com/doi/pdfdirect/{test_doi}?download=true"

        try:
            with page.expect_download(timeout=60000) as dl:
                try:
                    page.goto(test_url, wait_until="commit", timeout=30000)
                except Exception:
                    pass  # Download is starting
            dl.value.save_as("/tmp/ezproxy_test.pdf")
            logger.info("EZProxy already authenticated")
            self._load_cookies()
            page.close()
            return True
        except Exception:
            # Not authenticated — need SSO
            logger.info("EZProxy needs SSO login")
            page.goto(test_url, wait_until="commit", timeout=30000)

            # Poll for login completion (max 3 min)
            for i in range(180):
                time.sleep(1)
                url = page.url
                if "login" not in url and "sso" not in url.lower() and "idp" not in url.lower():
                    logger.info("SSO login detected")
                    self._load_cookies()
                    page.close()
                    return True

            logger.warning("SSO login timeout")
            page.close()
            return False

    # ── Download orchestrator ──

    def download_by_doi(self, doi: str, output_dir: str, oa_url: str = None) -> dict:
        doi = doi.strip()
        doi_safe = doi.replace("/", "_").replace(":", "_").replace(".", "_")
        output_path = str(Path(output_dir) / f"{doi_safe}.pdf")

        if Path(output_path).exists():
            return {"success": True, "path": output_path, "method": "cached", "error": None}

        # Strategy 1: Direct OA HTTP
        if oa_url and self.open_access_first:
            result = self._http_download(oa_url, output_path, "oa_direct")
            if result["success"]:
                return result

        # Strategy 2: Unpaywall
        if self.email:
            unpaywall_url = self._get_unpaywall_oa(doi)
            if unpaywall_url and unpaywall_url != oa_url:
                result = self._http_download(unpaywall_url, output_path, "unpaywall")
                if result["success"]:
                    return result

        # Strategy 3: ResearchGate
        rg_url = self._search_researchgate(doi)
        if rg_url:
            result = self._http_download(rg_url, output_path, "researchgate")
            if result["success"]:
                return result

        # Strategy 4: EZProxy direct PDF URLs (HTTP, must have cookies)
        if self._cookies:
            result = self._ezproxy_direct_pdf(doi, output_path)
            if result["success"]:
                return result

        # Strategy 5: Playwright browser (fallback for JS-heavy pages)
        if self._context:
            result = self._playwright_download(doi, output_path, oa_url)
            if result["success"]:
                return result

        # Strategy 6: DOI redirect chain via HTTP
        result = self._http_download(f"https://doi.org/{doi}", output_path, "doi_redirect")
        if result["success"]:
            return result

        return {"success": False, "path": None, "method": "exhausted", "error": "All download methods failed"}

    # ── HTTP download (requests, not Playwright) ──

    def _http_download(self, url: str, output_path: str, method: str) -> dict:
        try:
            resp = self.session.get(url, timeout=self.timeout, allow_redirects=True, stream=True)
            if resp.status_code == 200:
                content = resp.content
                ct = resp.headers.get("Content-Type", "")

                if b"%PDF" in content[:1024] or "pdf" in ct.lower():
                    with open(output_path, "wb") as f:
                        f.write(content)
                    logger.info(f"{method}: {url[:80]}")
                    return {"success": True, "path": output_path, "method": method, "error": None}

                # HTML page — try to extract PDF link
                if b"<html" in content[:1024].lower() or b"<!doctype" in content[:1024].lower():
                    pdf_url = self._extract_pdf_from_html(content, resp.url)
                    if pdf_url:
                        sub = self._http_download(pdf_url, output_path, f"{method}_extracted")
                        if sub["success"]:
                            return sub
        except requests.exceptions.Timeout:
            logger.debug(f"Timeout: {url[:80]}")
        except Exception as e:
            logger.debug(f"HTTP error: {e}")

        return {"success": False, "path": None, "method": method, "error": "HTTP download failed"}

    # ── EZProxy direct PDF via HTTP ──

    def _get_direct_pdf_url(self, doi: str) -> list[tuple[str, str]]:
        """Build direct PDF URLs that bypass publisher landing pages."""
        doi_lower = doi.lower()

        if "10.1111/" in doi_lower or "10.1002/" in doi_lower:
            return [(f"https://onlinelibrary.wiley.com/doi/pdfdirect/{doi}?download=true", "wiley")]
        if "10.1080/" in doi_lower:
            return [(f"https://www.tandfonline.com/doi/pdf/{doi}?download=true", "tandf")]
        if "10.1177/" in doi_lower:
            return [(f"https://journals.sagepub.com/doi/pdf/{doi}?download=true", "sage")]
        if "10.1093/" in doi_lower:
            return [
                (f"https://academic.oup.com/documentlibrary/doi/pdfdirect/{doi}", "oup_direct"),
                (f"https://academic.oup.com/journals/doi/pdf/{doi}", "oup_pdf"),
            ]
        if "10.1007/" in doi_lower:
            return [(f"https://link.springer.com/content/pdf/{doi}.pdf", "springer")]
        if "10.1017/" in doi_lower:
            return [(f"https://www.cambridge.org/core/services/aop-cambridge-core/content/view/{doi}", "cambridge")]
        if "10.1108/" in doi_lower:
            return [(f"https://www.emerald.com/insight/content/doi/{doi}/full/pdf", "emerald")]
        if "10.1016/" in doi_lower:
            return [(f"https://www.sciencedirect.com/science/article/pii/{doi.split('/')[-1]}/pdfft?md5=null&isDTMRedir=Y", "elsevier")]
        if "10.3390/" in doi_lower:
            # MDPI OA — try DOI redirect first (may need EZProxy if IP-blocked), then CDN
            suffix = doi.split("10.3390/")[-1]
            return [
                (f"https://mdpi-res.com/{suffix}/pdf", "mdpi_cdn"),
                (f"https://www.mdpi.com/{suffix}/pdf", "mdpi"),
            ]
        if "10.48550/" in doi_lower:
            return [(f"https://arxiv.org/pdf/{doi.split('/')[-1]}", "arxiv")]
        return []

    def _ezproxy_direct_pdf(self, doi: str, output_path: str) -> dict:
        """Try EZProxy direct PDF URLs via HTTP (with stored cookies)."""
        direct_urls = self._get_direct_pdf_url(doi)
        for pdf_url, method in direct_urls:
            ezproxy_url = f"{self.ezproxy_base}{pdf_url}"
            for url, label in [(ezproxy_url, f"ezproxy_{method}"), (pdf_url, f"direct_{method}")]:
                try:
                    resp = self.session.get(url, timeout=self.timeout, allow_redirects=True)
                    if resp.status_code == 200:
                        content = resp.content
                        if b"%PDF" in content[:1024] or len(content) > 50000:
                            with open(output_path, "wb") as f:
                                f.write(content)
                            logger.info(f"{label}: {url[:80]}")
                            return {"success": True, "path": output_path, "method": label, "error": None}
                except Exception:
                    continue
        return {"success": False, "path": None, "method": "ezproxy", "error": "EZProxy direct PDF failed"}

    # ── Playwright download (fallback) ──

    def _playwright_download(self, doi: str, output_path: str, oa_url: str = None) -> dict:
        """Playwright browser download for stubborn pages (short timeout per attempt)."""
        from playwright.sync_api import TimeoutError as PWTimeout

        page = None
        try:
            page = self._context.new_page()

            # Try direct PDF URLs first (via EZProxy)
            for pdf_url, method in self._get_direct_pdf_url(doi):
                ezproxy_url = f"{self.ezproxy_base}{pdf_url}"
                for url, label in [(ezproxy_url, f"pw_proxy_{method}"), (pdf_url, f"pw_direct_{method}")]:
                    try:
                        with page.expect_download(timeout=15000) as dl_info:
                            try:
                                page.goto(url, wait_until="commit", timeout=15000)
                            except Exception:
                                pass
                        download = dl_info.value
                        download.save_as(output_path)
                        if Path(output_path).stat().st_size > 1000:
                            with open(output_path, "rb") as f:
                                if b"%PDF" in f.read(1024):
                                    return {"success": True, "path": output_path, "method": label, "error": None}
                    except PWTimeout:
                        # Timeout — page didn't trigger download, likely bot check. Move on.
                        continue
                    except Exception:
                        continue

            # Traditional landing page approach (shorter timeouts)
            doi_url = f"https://doi.org/{doi}"
            proxy_url = f"{self.ezproxy_base}{doi_url}"

            for method, url in [("pw_proxy_doi", proxy_url), ("pw_direct_doi", doi_url)]:
                try:
                    resp = page.goto(url, wait_until="commit", timeout=20000)
                    if resp and resp.ok:
                        ct = resp.headers.get("content-type", "")
                        if "pdf" in ct.lower():
                            body = resp.body()
                            if b"%PDF" in body[:1024]:
                                with open(output_path, "wb") as f:
                                    f.write(body)
                                return {"success": True, "path": output_path, "method": method, "error": None}
                except PWTimeout:
                    continue
                except Exception:
                    continue

        except Exception as e:
            logger.debug(f"PW download error: {e}")
        finally:
            if page:
                page.close()

        return {"success": False, "path": None, "method": "playwright", "error": "PW download failed"}

    # ── HTML PDF extraction ──

    def _extract_pdf_from_html(self, content: bytes, base_url: str) -> str | None:
        try:
            html = content.decode("utf-8", errors="ignore")
        except Exception:
            return None

        match = re.search(
            r'<meta[^>]*citation_pdf_url["\']?\s*content=["\']([^"\']+)["\']',
            html, re.IGNORECASE,
        )
        if match:
            return urljoin(base_url, match.group(1))

        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "lxml")
            for a in soup.find_all("a", href=True):
                href = a["href"].lower()
                text = a.get_text().strip().lower()
                if href.endswith(".pdf") or "pdf" in text or "download" in text:
                    return urljoin(base_url, a["href"])
        except Exception:
            pass

        return None

    # ── Publisher URL mapping ──

    def _get_publisher_url(self, doi: str) -> str | None:
        doi_lower = doi.lower()
        if "10.1111/" in doi_lower or "10.1002/" in doi_lower:
            return f"https://onlinelibrary.wiley.com/doi/{doi}"
        elif "10.1080/" in doi_lower:
            return f"https://www.tandfonline.com/doi/full/{doi}"
        elif "10.1093/" in doi_lower:
            return f"https://academic.oup.com/doi/{doi}"
        elif "10.1016/" in doi_lower:
            return f"https://www.sciencedirect.com/science/article/pii/{doi.split('/')[-1]}"
        elif "10.1007/" in doi_lower:
            return f"https://link.springer.com/article/{doi}"
        elif "10.1017/" in doi_lower:
            return f"https://www.cambridge.org/core/journals/article/{doi}"
        elif "10.1177/" in doi_lower:
            return f"https://journals.sagepub.com/doi/{doi}"
        elif "10.1108/" in doi_lower:
            return f"https://www.emerald.com/insight/content/doi/{doi}"
        elif "10.3390/" in doi_lower:
            return f"https://www.mdpi.com/{doi.split('/')[-1]}"
        elif "10.1126/" in doi_lower:
            return f"https://www.science.org/doi/{doi}"
        elif "10.48550/" in doi_lower:
            return f"https://arxiv.org/abs/{doi.split('/')[-1]}"
        return None

    # ── ResearchGate & Unpaywall ──

    def _search_researchgate(self, doi: str) -> str | None:
        try:
            search_url = f"https://www.researchgate.net/search/publication?q={doi}"
            resp = self.session.get(search_url, timeout=self.timeout, allow_redirects=True)
            if resp.status_code != 200:
                return None
            pdf_matches = re.findall(r'https?://www\.researchgate\.net/[^"\'\s]+\.pdf[^"\'\s]*', resp.text)
            dl_matches = re.findall(r'https?://www\.researchgate\.net/[^"\'\s]+/_download[^"\'\s]*', resp.text)
            for url in pdf_matches + dl_matches:
                return url
            return None
        except Exception:
            return None

    def _get_unpaywall_oa(self, doi: str) -> str | None:
        try:
            url = f"https://api.unpaywall.org/v2/{doi}?email={self.email}"
            resp = self.session.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                best = data.get("best_oa_location") or {}
                return best.get("url") or best.get("url_for_pdf") or best.get("url_for_landing_page")
        except Exception:
            pass
        return None
