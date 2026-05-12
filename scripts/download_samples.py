#!/usr/bin/env python3
"""Randomly sample and download N papers from the candidate list."""

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

SAMPLE_SIZE = 30


def main():
    config = load_config()
    setup_logging(config)

    candidates_path = Path(__file__).parent.parent / "data" / "search_results" / "deduplicated_candidates.jsonl"
    with open(candidates_path) as f:
        candidates = [json.loads(line) for line in f if line.strip()]

    random.seed(42)
    sample = random.sample(candidates, min(SAMPLE_SIZE, len(candidates)))

    # Save sample list
    sample_list_path = Path(__file__).parent.parent / "output" / "sample_30.csv"
    with open(sample_list_path, "w") as f:
        f.write("Title,Authors,Year,Journal,DOI,OA\n")
        for p in sample:
            authors = "; ".join(a["name"] for a in p.get("authors", [])[:3])
            f.write(f'"{p.get("title", "")}","{authors}",{p.get("publication_year")},"{p.get("journal", "")}",https://doi.org/{p.get("doi")},{p.get("is_oa")}\n')

    logger.info(f"Randomly sampled {len(sample)} papers, saved list to {sample_list_path}")

    oa_count = sum(1 for p in sample if p.get("is_oa"))
    pw_count = len(sample) - oa_count
    logger.info(f"Sample: {oa_count} OA, {pw_count} paywalled")

    pdf_dir = Path(__file__).parent.parent / "data" / "pdfs"
    pdf_dir.mkdir(parents=True, exist_ok=True)

    headless = config.get("ezproxy", {}).get("headless", False)
    downloader = EZProxyDownloader(
        ezproxy_base=config.get("ezproxy", {}).get("base_url", "https://lib.ezproxy.ust.hk/login?url="),
        user_data_dir=config.get("ezproxy", {}).get("user_data_dir", "./auth/playwright_profile"),
        open_access_first=config.get("ezproxy", {}).get("open_access_first", True),
        timeout=config.get("ezproxy", {}).get("download_timeout_seconds", 60),
        headless=headless,
    )

    logger.info("Starting browser...")
    downloader.start()

    if not headless:
        print("\n" + "=" * 60)
        print("VISIBLE BROWSER -- Complete EZProxy login if prompted")
        print("Opening login page in 1s...")
        print("=" * 60 + "\n")
        time.sleep(1)
        page = downloader._context.new_page()
        page.goto("https://lib.ezproxy.hkust.edu.hk/login?url=https://doi.org/10.1111/puar.70098")
        print("Waiting 15s for login... (the browser window stays open)")
        time.sleep(15)
        page.close()

    results = []
    success = 0
    failed = 0

    try:
        for paper in tqdm(sample, desc="Downloading"):
            doi = paper.get("doi")
            oa_url = paper.get("oa_url") if paper.get("is_oa") else None
            result = downloader.download_by_doi(doi=doi, output_dir=str(pdf_dir), oa_url=oa_url)
            result["doi"] = doi
            result["title"] = paper.get("title", "")
            results.append(result)
            if result["success"]:
                success += 1
            else:
                failed += 1
    finally:
        downloader.stop()

    log_path = Path(__file__).parent.parent / "data" / "search_results" / "sample_download_log.jsonl"
    with open(log_path, "w") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\n{'='*60}")
    print(f"Download complete: {success}/{len(sample)} succeeded, {failed} failed")
    if failed:
        print(f"Failed papers:")
        for r in results:
            if not r["success"]:
                print(f"  - {r['doi']}: {r.get('error', 'unknown')}")
    print(f"\nPDFs saved to: {pdf_dir}")
    print(f"Sample list:   {sample_list_path}")
    print(f"Download log:  {log_path}")


if __name__ == "__main__":
    main()
