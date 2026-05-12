#!/usr/bin/env python3
"""Targeted retry: only Playwright+EZProxy path, longer timeouts, detailed errors."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.config_loader import load_config
from utils.logger import setup_logging
from utils.ezproxy_downloader import EZProxyDownloader
import logging

logger = logging.getLogger("paper_collector")


def main():
    config = load_config()
    setup_logging(config)

    # Load only still-failed papers
    retry_log = Path("data/search_results/retry_download_log.jsonl")
    with open(retry_log) as f:
        retry_results = [json.loads(l) for l in f if l.strip()]

    failed = [r for r in retry_results if not r["success"]]
    print(f"Retrying {len(failed)} still-failed papers with EZProxy+Playwright only\n")

    pdf_dir = Path("data/pdfs")

    # HEADLESS now — session cookies are saved
    downloader = EZProxyDownloader(
        ezproxy_base=config.get("ezproxy", {}).get("base_url",
            "https://lib.ezproxy.hkust.edu.hk/login?url="),
        user_data_dir=config.get("ezproxy", {}).get("user_data_dir",
            "./auth/playwright_profile"),
        open_access_first=False,  # Skip HTTP — go straight to Playwright
        timeout=90,
        headless=True,
    )

    downloader.start()

    results = []
    n_ok = 0

    for i, paper in enumerate(failed):
        doi = paper["doi"]
        title = paper.get("title", "")[:80]
        print(f"\n[{i+1}/{len(failed)}] {doi}")

        # Skip OA-first HTTP — go straight to Playwright which has EZProxy cookies
        from playwright.sync_api import TimeoutError as PWTimeout
        import time

        output_path = str(pdf_dir / f"{doi.replace('/', '_').replace('.', '_')}.pdf")
        if Path(output_path).exists():
            print(f"  Already cached")
            results.append({"doi": doi, "title": title, "success": True, "method": "cached", "error": None})
            n_ok += 1
            continue

        page = None
        ok = False
        last_error = ""

        try:
            page = downloader._context.new_page()
            page.set_default_timeout(90000)

            # Try EZProxy first (we have session)
            ez_url = f"{downloader.ezproxy_base}https://doi.org/{doi}"
            print(f"  EZProxy: {ez_url[:100]}...")

            resp = page.goto(ez_url, wait_until="commit", timeout=60000)
            if resp and resp.ok:
                ct = resp.headers.get("content-type", "")
                if "pdf" in ct.lower():
                    body = resp.body()
                    if b"%PDF" in body[:1024]:
                        with open(output_path, "wb") as f:
                            f.write(body)
                        print(f"  OK: direct PDF from EZProxy ({len(body)} bytes)")
                        results.append({"doi": doi, "title": title, "success": True, "method": "ezproxy_direct", "error": None})
                        n_ok += 1
                        ok = True
                        continue

            # Wait for page to fully load
            try:
                page.wait_for_load_state("networkidle", timeout=20000)
            except PWTimeout:
                pass
            time.sleep(1)

            # Try to find and click PDF button
            url_before = page.url
            try:
                with page.expect_download(timeout=15000) as dl:
                    selectors = [
                        'a[href$=".pdf"]',
                        'a:has-text("PDF")',
                        'a:has-text("Download PDF")',
                        'a:has-text("Download")',
                        'a:has-text("Full Text")',
                        'button:has-text("PDF")',
                        'a:has-text("View PDF")',
                        'a:has-text("Access PDF")',
                        '[data-testid="pdf-link"]',
                    ]
                    clicked = False
                    for sel in selectors:
                        try:
                            btn = page.locator(sel).first
                            if btn.is_visible(timeout=1000):
                                btn.click(timeout=2000)
                                clicked = True
                                break
                        except Exception:
                            continue

                    if not clicked:
                        raise PWTimeout("No PDF button found")

                download = dl.value
                download.save_as(output_path)
                print(f"  OK: clicked PDF button")
                results.append({"doi": doi, "title": title, "success": True, "method": "ezproxy_click", "error": None})
                n_ok += 1
                ok = True
                continue
            except PWTimeout:
                pass

            # Try extracting PDF URL from page HTML
            import re
            from bs4 import BeautifulSoup
            from urllib.parse import urljoin

            content = page.content()
            current_url = page.url
            found_pdf = None

            # citation_pdf_url meta
            match = re.search(
                r'<meta[^>]*citation_pdf_url["\']?\s*content=["\']([^"\']+)["\']',
                content, re.IGNORECASE
            )
            if match:
                found_pdf = urljoin(current_url, match.group(1))

            # PDF links
            if not found_pdf:
                soup = BeautifulSoup(content, "lxml")
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    text = a.get_text().strip().lower()
                    if href.lower().endswith(".pdf") or "pdf" in text or "download" in text:
                        found_pdf = urljoin(current_url, href)
                        break

            if found_pdf:
                print(f"  Found PDF link: {found_pdf[:100]}")
                resp = page.goto(found_pdf, wait_until="commit", timeout=30000)
                if resp and resp.ok:
                    body = resp.body()
                    if b"%PDF" in body[:1024]:
                        with open(output_path, "wb") as f:
                            f.write(body)
                        print(f"  OK: extracted PDF link ({len(body)} bytes)")
                        results.append({"doi": doi, "title": title, "success": True, "method": "ezproxy_extract", "error": None})
                        n_ok += 1
                        ok = True
                        continue

            last_error = f"Page URL: {current_url[:100]}, no PDF found"
            print(f"  FAIL: {last_error}")

        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"
            print(f"  ERROR: {last_error}")
        finally:
            if page:
                page.close()

        if not ok:
            results.append({"doi": doi, "title": title, "success": False, "method": "ezproxy_exhausted", "error": last_error})

    downloader.stop()

    # Save
    final_log = Path("data/search_results/final_retry_log.jsonl")
    with open(final_log, "w") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    total_pdfs = len(list(pdf_dir.glob("*.pdf")))
    print(f"\n{'='*60}")
    print(f"FINAL RETRY: {n_ok}/{len(failed)} succeeded")
    print(f"Total PDFs on disk: {total_pdfs}")

    if n_ok < len(failed):
        print(f"\nStill failed:")
        for r in results:
            if not r["success"]:
                print(f"  {r['doi']}: {r.get('error','?')[:120]}")


if __name__ == "__main__":
    main()
