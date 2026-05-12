#!/usr/bin/env python3
"""
Stage 4: Extract text from downloaded PDFs.

Uses PyMuPDF4LLM for two-column academic PDF handling,
with fallback to plain PyMuPDF.

Output: data/extracted_text/*.md + extraction_log.jsonl
"""

import json
import logging
import sys
from pathlib import Path

from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.config_loader import load_config
from utils.logger import setup_logging
from utils.pdf_extractor import extract_pdf_text

logger = logging.getLogger("paper_collector")


def main():
    config = load_config()
    setup_logging(config)

    stages = config.get("pipeline", {}).get("stages", {})
    if not stages.get("extract_text", True):
        logger.info("Stage 4 disabled in config (pipeline.stages.extract_text=false), skipping")
        return

    logger.info("=" * 60)
    logger.info("Stage 4: Extracting text from PDFs")
    logger.info("=" * 60)

    pdf_dir = Path(__file__).parent.parent / "data" / "pdfs"
    if not pdf_dir.exists() or not list(pdf_dir.glob("*.pdf")):
        logger.error("No PDFs found. Run 03_download_pdfs.py first.")
        sys.exit(1)

    pdf_files = sorted(pdf_dir.glob("*.pdf"))
    logger.info(f"Found {len(pdf_files)} PDFs to extract")

    output_dir = Path(__file__).parent.parent / "data" / "extracted_text"
    output_dir.mkdir(parents=True, exist_ok=True)

    min_len = config.get("extraction", {}).get("min_text_length", 500)

    results = []
    success_count = 0
    fail_count = 0

    for pdf_path in tqdm(pdf_files, desc="Extracting text"):
        result = extract_pdf_text(str(pdf_path), min_text_length=min_len)
        result["filename"] = pdf_path.name
        doi_safe = pdf_path.stem

        if result["text"]:
            # Save markdown
            md_path = output_dir / f"{doi_safe}.md"
            with open(md_path, "w") as f:
                f.write(result["text"])

            result["output_path"] = str(md_path)
            success_count += 1
        else:
            fail_count += 1
            logger.warning(f"Empty extraction: {pdf_path.name} - {result.get('error', 'unknown')}")

        results.append(result)

    # Save log
    log_path = Path(__file__).parent.parent / "data" / "extracted_text" / "extraction_log.jsonl"
    with open(log_path, "w") as f:
        for r in results:
            log_entry = {k: v for k, v in r.items() if k != "text"}
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    # ---- Stats ----
    method_counts = {}
    total_words = 0
    word_counts = []
    for r in results:
        m = r.get("method", "unknown")
        method_counts[m] = method_counts.get(m, 0) + 1
        wc = r.get("word_count", 0)
        total_words += wc
        word_counts.append(wc)

    avg_words = total_words / len(results) if results else 0
    word_counts.sort()
    median_words = word_counts[len(word_counts)//2] if word_counts else 0

    stats_path = Path(__file__).parent.parent / "output" / "extraction_stats.json"
    stats = {
        "stage": "04_extract_text",
        "pdfs_processed": len(pdf_files),
        "extracted_successfully": success_count,
        "failed": fail_count,
        "method_breakdown": method_counts,
        "words": {
            "total": total_words,
            "average": round(avg_words),
            "median": median_words,
            "min": word_counts[0] if word_counts else 0,
            "max": word_counts[-1] if word_counts else 0,
        },
    }
    with open(stats_path, "w") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"STAGE 4: Text Extraction — Summary Report")
    print(f"{'='*60}")
    print(f"  PDFs processed:      {len(pdf_files)}")
    print(f"  Extracted:           {success_count}")
    print(f"  Failed:              {fail_count}")
    print(f"\n  EXTRACTION METHOD")
    for m, c in sorted(method_counts.items(), key=lambda x: -x[1]):
        print(f"    {m}: {c}")
    print(f"\n  TEXT STATISTICS")
    print(f"    Total words:        {total_words:,}")
    print(f"    Average words/paper: {avg_words:,.0f}")
    print(f"    Median words/paper:  {median_words:,}")
    print(f"    Range:               {word_counts[0]:,} – {word_counts[-1]:,}")
    print(f"\n  OUTPUT FILES")
    print(f"    Extracted texts: {output_dir}")
    print(f"    Log:             {log_path}")
    print(f"    Stats:           {stats_path}")

    logger.info(f"Stage 4 complete: {success_count} extracted, {fail_count} failed")


if __name__ == "__main__":
    main()
