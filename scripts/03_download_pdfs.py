#!/usr/bin/env python3
"""
Stage 3: Download candidate paper PDFs.

Uses Playwright for reliable PDF access through publisher bot protection.
First run in non-headless mode: user logs into EZProxy via SSO + Duo.
Session is saved to auth/playwright_profile for headless reuse.

Output: data/pdfs/*.pdf + download_log.jsonl
"""

import json
import logging
import sys
from pathlib import Path

from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.config_loader import load_config
from utils.logger import setup_logging
from utils.ezproxy_downloader import EZProxyDownloader

logger = logging.getLogger("paper_collector")


def load_candidates() -> list[dict]:
    path = Path(__file__).parent.parent / "data" / "search_results" / "deduplicated_candidates.jsonl"
    if not path.exists():
        logger.error("deduplicated_candidates.jsonl not found. Run 02_search_papers.py first.")
        sys.exit(1)

    candidates = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                candidates.append(json.loads(line))
    return candidates


def main():
    config = load_config()
    setup_logging(config)

    stages = config.get("pipeline", {}).get("stages", {})
    if not stages.get("download_pdfs", True):
        logger.info("Stage 3 disabled in config (pipeline.stages.download_pdfs=false), skipping")
        return

    logger.info("=" * 60)
    logger.info("Stage 3: Downloading candidate PDFs")
    logger.info("=" * 60)

    candidates = load_candidates()
    max_papers = config.get("pipeline", {}).get("max_papers_to_download", 200)
    candidates = candidates[:max_papers]

    oa_count = sum(1 for c in candidates if c.get("is_oa"))
    pw_count = len(candidates) - oa_count
    logger.info(f"Loaded {len(candidates)} candidates ({oa_count} OA, {pw_count} paywalled)")

    pdf_dir = Path(__file__).parent.parent / "data" / "pdfs"
    pdf_dir.mkdir(parents=True, exist_ok=True)

    headless = config.get("ezproxy", {}).get("headless", True)
    downloader = EZProxyDownloader(
        ezproxy_base=config.get("ezproxy", {}).get("base_url", "https://lib.ezproxy.ust.hk/login?url="),
        user_data_dir=config.get("ezproxy", {}).get("user_data_dir", "./auth/playwright_profile"),
        open_access_first=config.get("ezproxy", {}).get("open_access_first", True),
        timeout=config.get("ezproxy", {}).get("download_timeout_seconds", 60),
        headless=headless,
    )

    if not headless:
        print("\n" + "=" * 60)
        print("VISIBLE BROWSER MODE")
        print("1. A Chrome window will open")
        print("2. Navigate to EZProxy and complete SSO + Duo login if needed")
        print("3. Once logged in, the script will download all papers automatically")
        print("4. The session is saved for future headless runs")
        print("=" * 60 + "\n")

    logger.info("Starting browser...")
    downloader.start()

    if not headless:
        # Let user authenticate via EZProxy
        print("Opening EZProxy for login...")
        page = downloader._context.new_page()
        page.goto("https://lib.ezproxy.hkust.edu.hk/login?url=https://doi.org/10.1111/puar.70098")
        input("\nComplete SSO + Duo login in the browser if prompted, then press Enter to continue...")
        page.close()

    results = []
    success_count = 0
    fail_count = 0

    try:
        for paper in tqdm(candidates, desc="Downloading PDFs"):
            doi = paper.get("doi")
            oa_url = paper.get("oa_url") if paper.get("is_oa") else None
            result = downloader.download_by_doi(doi=doi, output_dir=str(pdf_dir), oa_url=oa_url)
            result["doi"] = doi
            result["title"] = paper.get("title", "")
            results.append(result)

            if result["success"]:
                success_count += 1
            else:
                fail_count += 1
                logger.warning(f"Failed: {doi} - {result.get('error')}")
    finally:
        downloader.stop()

    # Save download log
    log_path = Path(__file__).parent.parent / "data" / "search_results" / "download_log.jsonl"
    with open(log_path, "w") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # ---- Method breakdown ----
    method_counts = {}
    for r in results:
        m = r.get("method", "unknown")
        method_counts[m] = method_counts.get(m, 0) + 1

    # Save stats
    stats_path = Path(__file__).parent.parent / "output" / "download_stats.json"
    stats = {
        "stage": "03_download_pdfs",
        "candidates": len(candidates),
        "oa_candidates": oa_count,
        "paywalled_candidates": pw_count,
        "downloaded": success_count,
        "failed": fail_count,
        "success_rate": f"{success_count}/{len(candidates)} ({100*success_count/len(candidates):.1f}%)",
        "method_breakdown": method_counts,
    }
    with open(stats_path, "w") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"STAGE 3: PDF Download — Summary Report")
    print(f"{'='*60}")
    print(f"  Candidates:          {len(candidates)}")
    print(f"  Downloaded:          {success_count}")
    print(f"  Failed:              {fail_count}")
    print(f"  Success rate:        {100*success_count/len(candidates):.1f}%")
    print(f"\n  METHOD BREAKDOWN")
    for m, c in sorted(method_counts.items(), key=lambda x: -x[1]):
        print(f"    {m}: {c}")
    print(f"\n  OUTPUT FILES")
    print(f"    PDFs:    {pdf_dir}")
    print(f"    Log:     {log_path}")
    print(f"    Stats:   {stats_path}")

    if fail_count > 0:
        print(f"\n  FAILURES ({fail_count}):")
        for r in results:
            if not r["success"]:
                print(f"    [{r.get('method', '?')}] {r['doi']}: {r.get('error', 'unknown')[:100]}")
        if fail_count > 10:
            print(f"    ... ({fail_count} total failures shown above)")

    logger.info(f"Stage 3 complete: {success_count} downloaded, {fail_count} failed")


if __name__ == "__main__":
    main()
