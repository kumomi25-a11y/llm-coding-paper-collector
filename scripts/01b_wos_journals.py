#!/usr/bin/env python3
"""
Stage 1-B: Build journal registry from WoS SSCI list (CSV).

Reads the WoS SSCI CSV, extracts PA & PP journals by category,
matches them to OpenAlex source IDs via ISSN.

Usage:
    python scripts/01b_wos_journals.py
    python scripts/01b_wos_journals.py --categories "Public Administration,Political Science"

Input: Social Sciences Citation Index (SSCI).csv (downloaded from mjl.clarivate.com)
Output: data/journals/wos_pa_pp_registry.json
"""

import csv
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.config_loader import load_config
from utils.logger import setup_logging
from utils.openalex_client import OpenAlexClient

logger = logging.getLogger("paper_collector")

# Default categories for PA & PP
DEFAULT_CATEGORIES = [
    "Public Administration",
    "Political Science",
    "Social Issues",
    "Health Policy & Services",
]

CSV_PATH = "Social Sciences Citation Index (SSCI).csv"


def parse_wos_csv(filepath: str, categories: list[str]) -> list[dict]:
    """Parse WoS SSCI CSV and return journals in target categories."""
    journals = []
    with open(filepath, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            title = (row.get("Journal title") or "").strip()
            issn = (row.get("ISSN") or "").strip()
            eissn = (row.get("eISSN") or "").strip()
            wos_cats = (row.get("Web of Science Categories") or "").strip()

            if not title:
                continue

            row_cats = set(c.strip() for c in wos_cats.split("|"))
            matched_cats = row_cats & set(categories)
            if not matched_cats:
                continue

            journals.append({
                "title": title,
                "issn": issn,
                "eissn": eissn,
                "categories": ", ".join(sorted(matched_cats)),
            })

    return journals


def match_to_openalex(journals: list[dict], oa_client) -> list[dict]:
    """Match journals to OpenAlex source IDs via ISSN."""
    matched = []
    not_found = []
    seen_ids = set()

    for j in journals:
        issn = j.get("issn", "")
        eissn = j.get("eissn", "")

        source = None
        for query_issn in [issn, eissn]:
            if not query_issn:
                continue
            try:
                resp = oa_client._get(
                    "https://api.openalex.org/sources",
                    params={"filter": f"issn:{query_issn}", "per_page": 3},
                )
                results = resp.get("results", [])
                if results:
                    source = results[0]
                    break
            except Exception:
                continue

        if source:
            sid = source["id"].replace("https://openalex.org/", "")
            if sid not in seen_ids:
                seen_ids.add(sid)
                matched.append({
                    "title": j["title"],
                    "wos_issn": issn,
                    "wos_eissn": eissn,
                    "wos_categories": j["categories"],
                    "openalex_source_id": sid,
                    "openalex_display_name": source.get("display_name"),
                    "openalex_issn_l": source.get("issn_l"),
                    "works_count": source.get("works_count", 0),
                })
        else:
            not_found.append(j["title"])

    logger.info(f"OpenAlex match: {len(matched)}/{len(journals)}")
    if not_found:
        logger.info(f"Not found ({len(not_found)}): {not_found[:10]}")

    return matched


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=str, default=None,
                        help="Path to WoS SSCI CSV (default: project root)")
    parser.add_argument("--categories", type=str, default=None,
                        help="Comma-separated WoS categories to include")
    args = parser.parse_args()

    config = load_config()
    setup_logging(config)

    csv_path = args.input or str(Path(__file__).parent.parent / CSV_PATH)
    if not Path(csv_path).exists():
        logger.error(f"CSV not found: {csv_path}")
        logger.error("Download from: https://mjl.clarivate.com/collection-list-downloads")
        return

    categories = [c.strip() for c in (args.categories or "").split(",") if c.strip()]
    if not categories:
        categories = DEFAULT_CATEGORIES

    logger.info("=" * 60)
    logger.info("Stage 1-B: WoS SSCI → OpenAlex Journal Registry")
    logger.info(f"Categories: {categories}")
    logger.info(f"Input: {csv_path}")
    logger.info("=" * 60)

    # Step 1: Parse CSV
    wos_journals = parse_wos_csv(csv_path, categories)
    logger.info(f"WoS journals in target categories: {len(wos_journals)}")

    # Step 2: Match to OpenAlex
    oa_client = OpenAlexClient(email=config.get("openalex", {}).get("email"))
    matched = match_to_openalex(wos_journals, oa_client)

    # Step 3: Compare with JCR PDF path
    jcr_path = Path(__file__).parent.parent / "data" / "journals" / "pa_journal_registry.json"
    jcr_issns = set()
    if jcr_path.exists():
        with open(jcr_path) as f:
            jcr_data = json.load(f)
        for j in jcr_data.get("found", []):
            if j.get("issn_l"):
                jcr_issns.add(j["issn_l"].lower())

    wos_issns = {j.get("openalex_issn_l", "").lower() for j in matched}
    overlap = jcr_issns & wos_issns
    jcr_only = jcr_issns - wos_issns
    wos_only = wos_issns - jcr_issns

    # Step 4: Save
    output = {
        "source": "WoS Master Journal List (SSCI)",
        "categories": categories,
        "total_matched": len(matched),
        "journals": matched,
        "comparison": {
            "jcr_pdf_count": len(jcr_issns),
            "wos_ssci_count": len(wos_issns),
            "overlap": len(overlap),
            "jcr_only_count": len(jcr_only),
            "wos_only_count": len(wos_only),
        },
    }

    output_path = Path(__file__).parent.parent / "data" / "journals" / "wos_pa_pp_registry.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # Print comparison
    comp = output["comparison"]
    print(f"\n{'='*60}")
    print(f"WoS SSCI vs JCR PDF — Comparison")
    print(f"{'='*60}")
    print(f"  WoS SSCI journals:        {comp['wos_ssci_count']}")
    print(f"  JCR PDF journals:          {comp['jcr_pdf_count']}")
    print(f"  Overlap (in both):         {comp['overlap']}")
    print(f"  JCR only (not in SSCI):   {comp['jcr_only_count']}")
    print(f"  WoS only (SSCI extras):   {comp['wos_only_count']}")
    print(f"\n  Note: JCR-only journals are in ESCI/other indexes but not SSCI")
    print(f"  Example: Lex localis is JCR-only (ESCI, not SSCI)")
    print(f"\nSaved to: {output_path}")

    logger.info("Stage 1-B complete")


if __name__ == "__main__":
    main()
