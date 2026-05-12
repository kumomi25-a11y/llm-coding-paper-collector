#!/usr/bin/env python3
"""Retry failed PDF downloads with visible browser for EZProxy SSO+Duo login."""

import json
import random
import sys
import time
from pathlib import Path

from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.config_loader import load_config
from utils.logger import setup_logging
from utils.ezproxy_downloader import EZProxyDownloader
import logging

logger = logging.getLogger("paper_collector")

TARGET_TOTAL = 30


def main():
    config = load_config()
    setup_logging(config)

    # Load previous download results
    prev_log = Path("data/search_results/sample_download_log.jsonl")
    prev_results = []
    if prev_log.exists():
        with open(prev_log) as f:
            prev_results = [json.loads(line) for line in f if line.strip()]

    failed_dois = set(r["doi"] for r in prev_results if not r["success"])
    already_success = sum(1 for r in prev_results if r["success"])
    already_tried = set(r["doi"] for r in prev_results)

    logger.info(f"Previous run: {already_success} succeeded, {len(failed_dois)} failed")

    # Load all candidates
    candidates_path = Path("data/search_results/deduplicated_candidates.jsonl")
    with open(candidates_path) as f:
        all_candidates = [json.loads(line) for line in f if line.strip()]

    candidates_by_doi = {c["doi"]: c for c in all_candidates}

    # Build retry list: all failed papers
    retry_papers = [candidates_by_doi[d] for d in failed_dois if d in candidates_by_doi]

    # Top up with fresh random papers to reach TARGET_TOTAL
    remaining_pool = [c for c in all_candidates if c["doi"] not in already_tried]
    needed = max(0, TARGET_TOTAL - already_success - len(retry_papers))
    random.seed(123)
    topup = random.sample(remaining_pool, min(needed, len(remaining_pool)))

    papers_to_try = retry_papers + topup
    oa = sum(1 for p in papers_to_try if p.get("is_oa"))
    pw = len(papers_to_try) - oa

    print(f"\nRetry plan: {len(retry_papers)} failed + {len(topup)} fresh = {len(papers_to_try)} papers")
    print(f"  OA: {oa}, Paywalled: {pw}")
    print(f"  After this run: up to {already_success + len(papers_to_try)} total PDFs")

    pdf_dir = Path("data/pdfs")
    pdf_dir.mkdir(parents=True, exist_ok=True)

    # --- HEADED browser for EZProxy login ---
    downloader = EZProxyDownloader(
        ezproxy_base=config.get("ezproxy", {}).get("base_url",
            "https://lib.ezproxy.ust.hk/login?url="),
        user_data_dir=config.get("ezproxy", {}).get("user_data_dir",
            "./auth/playwright_profile"),
        open_access_first=True,
        timeout=config.get("ezproxy", {}).get("download_timeout_seconds", 90),
        headless=False,
    )

    print("\n" + "=" * 60)
    print("  VISIBLE BROWSER OPENING — EZPROXY LOGIN REQUIRED")
    print("  1. Enter HKUST username + password on SSO page")
    print("  2. Approve Duo 2FA push notification")
    print("  3. Script auto-detects login and starts downloads")
    print("=" * 60 + "\n")

    downloader.start()

    page = downloader._context.new_page()
    page.goto(
        "https://lib.ezproxy.hkust.edu.hk/login?url=https://doi.org/10.1111/puar.70098",
        wait_until="commit",
        timeout=30000,
    )

    # Poll URL until login completes (max 3 min)
    print("Waiting for EZProxy login (max 3 min)...")
    logged_in = False
    for i in range(180):
        time.sleep(1)
        url = page.url
        # Done when URL leaves HKUST auth flow and lands on publisher content
        if "login" not in url and "sso" not in url.lower():
            print(f"\n  Login appears complete! URL: {url[:100]}")
            logged_in = True
            break
        if i > 0 and i % 20 == 0:
            print(f"  ...{i}s  current: {url[:90]}")

    if not logged_in:
        print(f"\n  Login timeout (180s). Final URL: {page.url[:120]}")
        print("  Proceeding with downloads anyway (session may still be saved)...")

    page.close()

    # --- Download ---
    results = []
    n_ok = 0
    n_fail = 0

    try:
        for paper in tqdm(papers_to_try, desc="Downloading"):
            doi = paper.get("doi")
            oa_url = paper.get("oa_url") if paper.get("is_oa") else None
            result = downloader.download_by_doi(doi=doi, output_dir=str(pdf_dir), oa_url=oa_url)
            result["doi"] = doi
            result["title"] = paper.get("title", "")
            results.append(result)
            if result["success"]:
                n_ok += 1
            else:
                n_fail += 1
    finally:
        downloader.stop()

    # Save retry log
    retry_log = Path("data/search_results/retry_download_log.jsonl")
    with open(retry_log, "w") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Merge with previous results for full picture
    full_results = prev_results + results

    # Summary
    total_ok = sum(1 for r in full_results if r["success"])
    total_pdfs = len(list(pdf_dir.glob("*.pdf")))

    print(f"\n{'='*60}")
    print(f"THIS RUN:  {n_ok}/{len(papers_to_try)} succeeded, {n_fail} failed")
    print(f"OVERALL:   {total_ok} PDFs in data/pdfs/ ({total_pdfs} files on disk)")

    if n_fail:
        print(f"\nStill failed ({n_fail}):")
        for r in results:
            if not r["success"]:
                print(f"  [{r.get('method','?')}] {r['doi']}  {r.get('title','')[:70]}")

    # Method breakdown
    methods = {}
    for r in full_results:
        if r["success"]:
            m = r.get("method", "?")
            methods[m] = methods.get(m, 0) + 1
    print(f"\nMethod breakdown (successes):")
    for m, c in sorted(methods.items(), key=lambda x: -x[1]):
        print(f"  {m}: {c}")

    print(f"\nRetry log: {retry_log}")


if __name__ == "__main__":
    main()
