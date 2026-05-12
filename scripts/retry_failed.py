#!/usr/bin/env python3
"""
Retry failed PDF downloads.

1. Opens visible browser for EZProxy SSO login (one-time)
2. Extracts cookies
3. Downloads ALL failed papers via HTTP + EZProxy direct PDF URLs (no bot detection)
4. Fast — no landing pages, no browser navigation per paper

Usage:
    python scripts/retry_failed.py
"""

import json
import sys
from pathlib import Path

from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.ezproxy_downloader import EZProxyDownloader
from utils.config_loader import load_config
from utils.logger import setup_logging


def main():
    config = load_config()
    setup_logging(config)

    # Load failed DOIs
    log_path = Path("data/search_results/download_log.jsonl")
    if not log_path.exists():
        print("No download log found.")
        return

    with open(log_path) as f:
        results = [json.loads(line) for line in f if line.strip()]

    failed_dois = [r["doi"] for r in results if not r["success"]]
    print(f"Failed papers: {len(failed_dois)}")

    candidates_path = Path("data/search_results/deduplicated_candidates.jsonl")
    with open(candidates_path) as f:
        candidates = {json.loads(line)["doi"]: json.loads(line) for line in f if line.strip()}

    # EZProxy downloader — Playwright just for SSO, downloads via HTTP
    downloader = EZProxyDownloader(
        ezproxy_base="https://lib.ezproxy.hkust.edu.hk/login?url=",
        user_data_dir="./auth/playwright_profile",
        open_access_first=False,
        timeout=30,
        headless=False,  # Visible for SSO
    )
    downloader.start()

    # Step 1: EZProxy SSO login (visible browser)
    print("\n" + "=" * 60)
    print("  EZPROXY LOGIN — Complete SSO + Duo if prompted")
    print("  A Chrome window will open...")
    print("=" * 60 + "\n")
    logged_in = downloader.ezproxy_login()

    if not logged_in:
        print("\n>>> SSO login not detected after 3 minutes.")
        print(">>> Continuing anyway — some papers may download if cookies exist.\n")

    # Step 2: Batch HTTP download via EZProxy direct PDF URLs
    pdf_dir = Path("data/pdfs")
    retry_results = []
    success = 0
    fail = 0

    for doi in tqdm(failed_dois, desc="Downloading"):
        r = downloader.download_by_doi(doi=doi, output_dir=str(pdf_dir), oa_url=None)
        r["doi"] = doi
        r["title"] = candidates.get(doi, {}).get("title", "")
        retry_results.append(r)
        if r["success"]:
            success += 1
        else:
            fail += 1

    downloader.stop()

    # Save retry log
    with open("data/search_results/retry_download_log.jsonl", "w") as f:
        for r in retry_results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Merge results
    all_results = {r["doi"]: r for r in results}
    for r in retry_results:
        if r["success"]:
            all_results[r["doi"]] = r

    still_failed = [r for r in retry_results if not r["success"]]
    total_pdfs = len(list(pdf_dir.glob("*.pdf")))

    print(f"\n{'='*60}")
    print(f"RETRY COMPLETE")
    print(f"{'='*60}")
    print(f"  This run:    {success} OK, {fail} failed")
    print(f"  Total PDFs:  {total_pdfs} / 181")

    if still_failed:
        with open("output/still_failed_dois.txt", "w") as f:
            for r in still_failed:
                f.write(f"{r['doi']}\n")

        with open("output/manual_download_urls.txt", "w") as f:
            f.write("# Manual download URLs (open each in browser after EZProxy login)\n\n")
            for r in still_failed:
                doi = r["doi"]
                c = candidates.get(doi, {})
                f.write(f"# {c.get('title', '?')[:80]}\n")
                f.write(f"https://lib.ezproxy.hkust.edu.hk/login?url=https://doi.org/{doi}\n\n")

        print(f"\n  Still failed: {len(still_failed)}")
        for r in still_failed[:10]:
            print(f"    {r['doi']}  [{r.get('method','?')}]")
        if len(still_failed) > 10:
            print(f"    ... and {len(still_failed)-10} more")
        print(f"\n  Saved: output/still_failed_dois.txt")
        print(f"  Saved: output/manual_download_urls.txt")


if __name__ == "__main__":
    main()
