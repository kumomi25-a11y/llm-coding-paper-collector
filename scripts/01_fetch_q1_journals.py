#!/usr/bin/env python3
"""
Stage 1: Fetch Public Administration journals.

Discovers journals that publish works in the Public Administration subfield
(OpenAlex subfield ID 3321), then enriches with source metadata.

Output: data/journals/q1_journals.json
"""

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.config_loader import load_config
from utils.logger import setup_logging
from utils.openalex_client import OpenAlexClient

logger = logging.getLogger("paper_collector")

# All Public Administration journals from JCR 2025 (Q1-Q4, 89 journals)
# Source: journal_list_pa.pdf — Journal Citation Reports 2025, 公共管理类期刊共90种
def _load_pa_journals() -> dict:
    """Load PA journal list from JSON file (built from journal_list_pa.pdf)."""
    import json
    json_path = Path(__file__).parent.parent / "data" / "journals" / "pa_journals_all.json"
    if json_path.exists():
        with open(json_path) as f:
            return json.load(f)
    raise FileNotFoundError(f"PA journal list not found at {json_path}. Run build script first.")

KNOWN_PA_JOURNALS = _load_pa_journals()


def match_known_q1(name: str) -> str | None:
    """Check if a journal name matches a known Q1 journal. Uses word overlap."""
    name_lower = name.lower().strip()
    name_words = set(name_lower.split())

    best_match = None
    best_score = 0

    for key, canonical in KNOWN_PA_JOURNALS.items():
        key_words = set(key.split())

        # Require strong overlap: Jaccard >= 0.5 or key fully contained
        intersection = name_words & key_words
        union = name_words | key_words
        jaccard = len(intersection) / len(union) if union else 0

        # Also check: all key words present in name (acronyms handled)
        key_in_name = key_words.issubset(name_words)

        if jaccard >= 0.5 or key_in_name:
            if jaccard > best_score:
                best_score = jaccard
                best_match = canonical

    # Only return if the name is actually close (exclude substring-only false positives)
    if best_match and best_score >= 0.4:
        return best_match
    return None


def main():
    config = load_config()
    setup_logging(config)

    stages = config.get("pipeline", {}).get("stages", {})
    if not stages.get("fetch_journals", True):
        logger.info("Stage 1 disabled in config (pipeline.stages.fetch_journals=false), skipping")
        return

    logger.info("=" * 60)
    logger.info("Stage 1: Discovering Public Administration journals")
    logger.info("=" * 60)

    oa_client = OpenAlexClient(
        email=config.get("openalex", {}).get("email", "your_email@ust.hk")
    )

    # Discover all journals with works in subfield 3321
    discovered = oa_client.get_journals_by_subfield(subfield_ids=[3321])

    # Tag known Q1 journals and flag others
    tagged = []
    for j in discovered:
        matched = match_known_q1(j["name"])
        j["matched_q1"] = matched if matched else None
        j["quartile"] = "Q1" if matched else "unknown"
        tagged.append(j)

    q1_matched = [j for j in tagged if j["matched_q1"]]
    unknown = [j for j in tagged if not j["matched_q1"]]

    logger.info(f"Known Q1 matches: {len(q1_matched)}")
    logger.info(f"Other journals in subfield: {len(unknown)}")

    # Save all journals (Q1 tag enables filtering later)
    output_path = Path(__file__).parent.parent / "data" / "journals" / "q1_journals.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(tagged, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"Stage 1 complete: {len(tagged)} journals found")
    print(f"  Known Q1 journals:   {len(q1_matched)}")
    print(f"  Other PA journals:   {len(unknown)}")
    print(f"\nQ1 journals:")
    for j in q1_matched:
        src_id = j.get("openalex_source_id", "N/A")
        print(f"  [{src_id:>12}] {j['matched_q1']}")
    if unknown:
        print(f"\nOther journals (not in known Q1 list, but publish in PA subfield):")
        for j in unknown[:20]:
            src_id = j.get("openalex_source_id", "N/A")
            print(f"  [{src_id:>12}] {j['name']}")
        if len(unknown) > 20:
            print(f"  ... and {len(unknown) - 20} more")
    print(f"\nSaved to: {output_path}")

    logger.info(f"Stage 1 complete: {len(tagged)} journals")


if __name__ == "__main__":
    main()
