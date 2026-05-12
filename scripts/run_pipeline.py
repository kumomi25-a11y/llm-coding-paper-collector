#!/usr/bin/env python3
"""
Pipeline Runner: Execute all stages sequentially with unified reporting.

Usage:
    python scripts/run_pipeline.py              # All stages
    python scripts/run_pipeline.py --stages 2   # Stage 2 only
    python scripts/run_pipeline.py --stages 2,3,4  # Specific stages
    python scripts/run_pipeline.py --skip-s2    # Skip Semantic Scholar

Reads pipeline.stages toggles from config.yaml (overridden by --stages).
"""

import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.config_loader import load_config
from utils.logger import setup_logging

logger = logging.getLogger("paper_collector")


def run_stage(script_name: str, stage_num: int, config: dict) -> dict:
    """Run a single pipeline stage and return timing/success."""
    stages = config.get("pipeline", {}).get("stages", {})
    stage_keys = {1: "fetch_journals", 2: "search_papers", 3: "download_pdfs", 4: "extract_text"}
    key = stage_keys.get(stage_num)

    if key and not stages.get(key, True):
        logger.info(f"Stage {stage_num} disabled in config, skipping")
        return {"stage": stage_num, "ran": False, "reason": "disabled_in_config"}

    import subprocess

    script_path = Path(__file__).parent / script_name
    if not script_path.exists():
        return {"stage": stage_num, "ran": False, "reason": f"script not found: {script_name}"}

    logger.info(f"\n{'#'*60}")
    logger.info(f"# Running Stage {stage_num}: {script_name}")
    logger.info(f"{'#'*60}")

    t0 = time.time()
    result = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=True, text=True, timeout=1200,
    )
    elapsed = time.time() - t0

    if result.returncode != 0:
        logger.error(f"Stage {stage_num} failed (exit {result.returncode})")
        logger.error(f"STDERR: {result.stderr[-500:]}")

    return {
        "stage": stage_num,
        "script": script_name,
        "ran": True,
        "success": result.returncode == 0,
        "elapsed_seconds": round(elapsed, 1),
        "stdout_tail": result.stdout[-500:] if result.stdout else "",
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Run the LLM paper collection pipeline")
    parser.add_argument("--stages", type=str, default="1,2,3,4",
                        help="Comma-separated stage numbers to run (default: 1,2,3,4)")
    parser.add_argument("--start", type=int, default=1,
                        help="Start from this stage (overrides --stages)")
    args = parser.parse_args()

    config = load_config()
    setup_logging(config)

    # Parse stage selection
    if args.start > 1:
        stage_nums = list(range(args.start, 5))
    else:
        stage_nums = [int(s.strip()) for s in args.stages.split(",")]

    logger.info("=" * 60)
    logger.info("LLM Coding Paper Collector — Pipeline Runner")
    logger.info(f"Stages to run: {stage_nums}")
    logger.info("=" * 60)

    STAGE_SCRIPTS = {
        1: "01_fetch_q1_journals.py",
        2: "02_search_papers.py",
        3: "03_download_pdfs.py",
        4: "04_extract_text.py",
    }

    t_start = time.time()
    results = []

    for sn in stage_nums:
        script = STAGE_SCRIPTS.get(sn)
        if not script:
            logger.warning(f"Unknown stage {sn}, skipping")
            continue
        r = run_stage(script, sn, config)
        results.append(r)
        if r.get("stdout_tail"):
            print(r["stdout_tail"])

    total_elapsed = time.time() - t_start

    # ---- Unified Pipeline Summary ----
    print(f"\n{'='*70}")
    print(f"PIPELINE COMPLETE — Total elapsed: {total_elapsed/60:.1f} min")
    print(f"{'='*70}")

    for r in results:
        status = "OK" if r.get("success") else ("SKIP" if not r.get("ran") else "FAIL")
        elapsed = r.get("elapsed_seconds", 0)
        print(f"  Stage {r['stage']}: {status}  ({elapsed:.0f}s)  {r.get('reason', r.get('script', ''))}")

    # Try to print combined stats from output JSON files
    stats_files = [
        ("output/search_stats.json", "Stage 2: Paper Search"),
        ("output/download_stats.json", "Stage 3: PDF Downloads"),
        ("output/extraction_stats.json", "Stage 4: Text Extraction"),
    ]
    for path, label in stats_files:
        full_path = Path(__file__).parent.parent / path
        if full_path.exists():
            with open(full_path) as f:
                data = json.load(f)

    # Final counts
    candidates_path = Path(__file__).parent.parent / "data" / "search_results" / "deduplicated_candidates.jsonl"
    pdf_dir = Path(__file__).parent.parent / "data" / "pdfs"
    text_dir = Path(__file__).parent.parent / "data" / "extracted_text"

    n_candidates = sum(1 for _ in open(candidates_path)) if candidates_path.exists() else 0
    n_pdfs = len(list(pdf_dir.glob("*.pdf"))) if pdf_dir.exists() else 0
    n_texts = len(list(text_dir.glob("*.md"))) if text_dir.exists() else 0

    print(f"\n  FINAL COUNTS")
    print(f"    Candidate papers:     {n_candidates}")
    print(f"    PDFs downloaded:      {n_pdfs}")
    print(f"    Texts extracted:      {n_texts}")
    print(f"    Pipeline duration:    {total_elapsed/60:.1f} minutes")


if __name__ == "__main__":
    main()
