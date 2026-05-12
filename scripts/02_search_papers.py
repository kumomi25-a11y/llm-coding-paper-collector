#!/usr/bin/env python3
"""
Stage 2: Search for candidate papers mentioning LLM coding.

Searches OpenAlex (full-text n-grams) and Semantic Scholar (snippets)
for papers published 2024+ in Q1 Public Administration journals.

Output: data/search_results/deduplicated_candidates.jsonl
"""

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.config_loader import load_config
from utils.logger import setup_logging
from utils.openalex_client import OpenAlexClient
from utils.semantic_scholar_client import SemanticScholarClient

logger = logging.getLogger("paper_collector")


def load_q1_journals() -> list[dict]:
    journal_path = Path(__file__).parent.parent / "data" / "journals" / "q1_journals.json"
    if not journal_path.exists():
        logger.error("q1_journals.json not found. Run 01_fetch_q1_journals.py first.")
        sys.exit(1)
    with open(journal_path) as f:
        return json.load(f)


def deduplicate_by_doi(papers: list[dict]) -> list[dict]:
    """Merge papers from multiple sources, keeping the most complete record."""
    seen = {}
    for p in papers:
        doi = p["doi"].lower().strip()
        if doi not in seen:
            seen[doi] = p
        else:
            # Merge: keep richer record
            existing = seen[doi]
            if not existing.get("abstract") and p.get("abstract"):
                existing["abstract"] = p["abstract"]
            if not existing.get("is_oa") and p.get("is_oa"):
                existing["is_oa"] = p["is_oa"]
                existing["oa_url"] = p.get("oa_url")
            if not existing.get("s2_snippet") and p.get("s2_snippet"):
                existing["s2_snippet"] = p["s2_snippet"]
                existing["s2_source_section"] = p.get("s2_source_section")
            # Track all sources
            existing["sources"] = list(set(existing.get("sources", [existing.get("source", "")]) + [p.get("source", "")]))

    deduped = list(seen.values())
    # Ensure 'sources' is set
    for p in deduped:
        if "sources" not in p:
            p["sources"] = [p.get("source", "unknown")]

    logger.info(f"Deduplication: {len(papers)} → {len(deduped)} unique papers")
    return deduped


def _derive_s2_keywords(config_queries: list[str]) -> list[str]:
    """Derive high-impact keyword pairs for S2 paper/search.

    S2 paper/search uses simple phrase queries (not AND/OR logic).
    We select top LLM terms × top method terms. Each call costs API credits,
    so we keep this list short and targeted (~12 pairs).
    """
    llm_terms = [
        "LLM", "large language model", "ChatGPT", "GPT-4",
        "Claude", "DeepSeek", "generative AI", "AI-assisted",
    ]

    method_terms = ["coding", "thematic analysis", "content analysis"]

    keywords = []
    for llm in llm_terms:
        for method in method_terms[:2]:  # top 2 methods only
            keywords.append(f"{llm} {method}")
    return keywords


def filter_by_journal(papers: list[dict], pa_journals: list[dict]) -> list[dict]:
    """Keep only papers published in PA journals (by ISSN-L or journal name)."""
    pa_issns = set()
    pa_names = set()
    for j in pa_journals:
        if j.get("issn_l"):
            pa_issns.add(j["issn_l"].lower())
        if j.get("name"):
            pa_names.add(j["name"].lower())

    filtered = []
    unmatched = []
    for p in papers:
        issn = (p.get("journal_issn_l") or "").lower()
        name = (p.get("journal") or "").lower()

        # Exact ISSN match
        if issn and issn in pa_issns:
            filtered.append(p)
            continue
        # Exact name match
        if name and name in pa_names:
            filtered.append(p)
            continue
        # Fuzzy name match (only when name is non-empty)
        if name:
            matched = False
            for qn in pa_names:
                if len(qn) > 5 and (qn in name or name in qn):
                    filtered.append(p)
                    matched = True
                    break
            if matched:
                continue

        unmatched.append(p)

    if unmatched:
        logger.info(f"Journal filter excluded {len(unmatched)} papers (no PA journal match)")
        for p in unmatched[:5]:
            logger.debug(f"  Excluded: {p.get('journal','?')} | {p.get('doi','?')[:50]}")

    logger.info(f"Journal filter: {len(papers)} → {len(filtered)} (PA journals only)")
    return filtered


def main():
    config = load_config()
    setup_logging(config)

    # Respect pipeline stage toggle
    stages = config.get("pipeline", {}).get("stages", {})
    if not stages.get("search_papers", True):
        logger.info("Stage 2 disabled in config (pipeline.stages.search_papers=false), skipping")
        return

    logger.info("=" * 60)
    logger.info("Stage 2: Searching for candidate papers")
    logger.info("=" * 60)

    # Load PA journal registry (directly matched from PDF list, not subfield discovery)
    registry_path = Path(__file__).parent.parent / "data" / "journals" / "pa_journal_registry.json"
    if not registry_path.exists():
        logger.error("pa_journal_registry.json not found. Run journal lookup first.")
        return
    with open(registry_path) as f:
        registry = json.load(f)
    pa_matched = registry.get("found", [])
    source_ids = [j["openalex_source_id"] for j in pa_matched if j.get("openalex_source_id")]
    source_ids = list(dict.fromkeys(source_ids))
    logger.info(f"PA journals: {len(pa_matched)} of {len(pa_matched) + len(registry.get('not_found', []))} found, {len(source_ids)} source IDs for search")

    queries = config.get("search", {}).get("queries", [])

    # Initialize clients
    oa_client = OpenAlexClient(
        email=config.get("openalex", {}).get("email", "your_email@ust.hk")
    )
    s2_config = config.get("semantic_scholar", {})
    s2_client = SemanticScholarClient(
        api_key=s2_config.get("api_key"),
        max_results=s2_config.get("max_results_per_query", 1000),
    )

    all_papers = []

    # ---- Per-query tracking ----
    oa_query_stats = {}
    s2_query_stats = {}

    # Search OpenAlex (full-text n-grams: title + abstract + key phrases)
    logger.info(f"Searching OpenAlex with {len(queries)} queries across {len(source_ids)} source IDs...")
    for i, query in enumerate(queries):
        # Build short label for this query
        qlabel = f"Q{i+1}_OA"
        try:
            papers = oa_client.search_works(query, source_ids=source_ids)
            all_papers.extend(papers)
            oa_query_stats[qlabel] = {"query": query[:80], "hits": len(papers)}
            logger.info(f"  {qlabel}: {len(papers)} papers")
        except Exception as e:
            oa_query_stats[qlabel] = {"query": query[:80], "hits": 0, "error": str(e)}
            logger.error(f"  {qlabel} failed: {e}")

    # Search Semantic Scholar full-text snippets
    s2_enabled = s2_config.get("enabled", True)
    s2_total_hits = 0
    s2_success_count = 0
    s2_fail_count = 0
    if s2_enabled:
        logger.info(f"Searching Semantic Scholar snippets with {len(queries)} queries (snippet/search, full text)...")
        for i, query in enumerate(queries):
            qlabel = f"Q{i+1}_S2"
            try:
                snippets = s2_client.snippet_search(query)
                if snippets:
                    all_papers.extend(snippets)
                    s2_total_hits += len(snippets)
                    s2_success_count += 1
                s2_query_stats[qlabel] = {"query": query[:80], "hits": len(snippets)}
                logger.info(f"  {qlabel}: {len(snippets)} papers")
            except Exception as e:
                s2_query_stats[qlabel] = {"query": query[:80], "hits": 0, "error": str(e)[:60]}
                s2_fail_count += 1

        logger.info(f"S2 summary: {s2_success_count}/{s2_success_count + s2_fail_count} OK, {s2_total_hits} total hits")
    else:
        logger.info("Semantic Scholar disabled in config (semantic_scholar.enabled=false)")

    # ---- Enrich S2 papers with OA metadata (journal name, ISSN) via DOI lookup ----
    s2_papers = [p for p in all_papers if p.get("source") == "semantic_scholar" and not p.get("journal")]
    if s2_papers:
        logger.info(f"Enriching {len(s2_papers)} S2 papers via OA DOI lookup...")
        enriched_count = 0
        for p in s2_papers:
            doi = p.get("doi", "")
            if not doi:
                continue
            oa_meta = oa_client.get_work_by_doi(doi)
            if oa_meta:
                if oa_meta.get("journal"):
                    p["journal"] = oa_meta["journal"]
                if oa_meta.get("journal_issn_l"):
                    p["journal_issn_l"] = oa_meta["journal_issn_l"]
                if oa_meta.get("abstract") and not p.get("abstract"):
                    p["abstract"] = oa_meta["abstract"]
                if oa_meta.get("is_oa") and not p.get("is_oa"):
                    p["is_oa"] = oa_meta["is_oa"]
                    p["oa_url"] = oa_meta.get("oa_url")
                enriched_count += 1
        logger.info(f"Enriched {enriched_count}/{len(s2_papers)} S2 papers with OA metadata")

    # ---- Pre-dedup source breakdown ----
    oa_raw = sum(1 for p in all_papers if p.get("source") == "openalex")
    s2_raw = sum(1 for p in all_papers if p.get("source") == "semantic_scholar")
    logger.info(f"Before dedup: {len(all_papers)} total ({oa_raw} OA + {s2_raw} S2)")

    # Deduplicate by DOI (this merges OA + S2 papers sharing the same DOI)
    deduped = deduplicate_by_doi(all_papers)

    # Filter results to PA journals only (using registry names/ISSNs)
    filtered = filter_by_journal(deduped, pa_matched)

    # ---- Post-filter source breakdown ----
    oa_final = sum(1 for p in filtered if "openalex" in p.get("sources", []))
    s2_final = sum(1 for p in filtered if "semantic_scholar" in p.get("sources", []))
    both_final = sum(1 for p in filtered if "openalex" in p.get("sources", []) and "semantic_scholar" in p.get("sources", []))
    oa_only = oa_final - both_final
    s2_only = s2_final - both_final

    # ---- Journal distribution ----
    journal_counts = {}
    for p in filtered:
        jname = p.get("journal", "Unknown")
        journal_counts[jname] = journal_counts.get(jname, 0) + 1
    top_journals = sorted(journal_counts.items(), key=lambda x: -x[1])[:10]

    # ---- Year distribution ----
    year_counts = {}
    for p in filtered:
        y = p.get("publication_year", "?")
        year_counts[y] = year_counts.get(y, 0) + 1

    # Save candidates
    output_path = Path(__file__).parent.parent / "data" / "search_results" / "deduplicated_candidates.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for paper in filtered:
            f.write(json.dumps(paper, ensure_ascii=False) + "\n")

    # Save CSV
    csv_path = Path(__file__).parent.parent / "output" / "search_results.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    import pandas as pd
    df = pd.DataFrame(filtered)
    if not df.empty:
        cols = ["doi", "title", "publication_year", "journal", "is_oa", "cited_by_count", "sources"]
        df_out = df[[c for c in cols if c in df.columns]]
        df_out.to_csv(csv_path, index=False)

    # Save detailed query stats
    stats_path = Path(__file__).parent.parent / "output" / "search_stats.json"
    stats = {
        "stage": "02_search_papers",
        "journal_registry": {
            "total_in_registry": len(pa_matched) + len(registry.get("not_found", [])),
            "matched_to_openalex": len(pa_matched),
            "not_found": len(registry.get("not_found", [])),
            "source_ids_for_search": len(source_ids),
        },
        "queries_run": len(queries),
        "openalex_per_query": oa_query_stats,
        "semantic_scholar_enabled": s2_enabled,
        "semantic_scholar_success_rate": f"{s2_success_count}/{s2_success_count + s2_fail_count}" if (s2_success_count + s2_fail_count) > 0 else "N/A",
        "semantic_scholar_per_query": s2_query_stats,
        "before_dedup": {"total": len(all_papers), "openalex": oa_raw, "semantic_scholar": s2_raw},
        "after_dedup": len(deduped),
        "after_journal_filter": len(filtered),
        "source_breakdown": {
            "openalex_total": oa_final,
            "semantic_scholar_total": s2_final,
            "both_sources": both_final,
            "openalex_only": oa_only,
            "semantic_scholar_only": s2_only,
        },
        "oa_vs_paywalled": {
            "open_access": sum(1 for p in filtered if p.get("is_oa")),
            "paywalled": sum(1 for p in filtered if not p.get("is_oa")),
        },
        "top_journals": [{"journal": j, "papers": c} for j, c in top_journals],
        "year_distribution": year_counts,
    }
    with open(stats_path, "w") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    # ---- Print detailed summary ----
    print(f"\n{'='*60}")
    print(f"STAGE 2: Paper Search — Summary Report")
    print(f"{'='*60}")
    print(f"\n  JOURNALS")
    print(f"    In registry:        {len(pa_matched) + len(registry.get('not_found', []))}")
    print(f"    Matched (OA ID):    {len(pa_matched)}")
    print(f"    Source IDs used:    {len(source_ids)}")
    print(f"\n  OPENALEX ({len(queries)} queries)")
    for ql, qs in oa_query_stats.items():
        err = f"  [FAILED: {qs.get('error', '')}]" if "error" in qs else ""
        print(f"    {ql}: {qs['hits']} papers{err}")
    print(f"\n  SEMANTIC SCHOLAR (enabled={s2_enabled})")
    if s2_enabled:
        print(f"    Snippet queries:    {s2_success_count} OK, {s2_fail_count} rate-limited")
        print(f"    Total S2 hits:      {s2_total_hits}")
    else:
        print(f"    (disabled)")
    print(f"\n  DEDUPLICATION")
    print(f"    Before:             {len(all_papers)} raw hits ({oa_raw} OA + {s2_raw} S2)")
    print(f"    After dedup:        {len(deduped)} unique")
    print(f"    After journal filt: {len(filtered)} in PA journals")
    print(f"\n  SOURCE OVERLAP")
    print(f"    OpenAlex only:      {oa_only}")
    print(f"    S2 only:            {s2_only}")
    print(f"    Both sources:       {both_final}")
    print(f"\n  ACCESS")
    print(f"    Open Access:        {sum(1 for p in filtered if p.get('is_oa'))}")
    print(f"    Paywalled:          {sum(1 for p in filtered if not p.get('is_oa'))}")
    print(f"\n  YEAR DISTRIBUTION")
    for y in sorted(year_counts.keys()):
        print(f"    {y}: {year_counts[y]} papers")
    print(f"\n  TOP JOURNALS")
    for j, c in top_journals:
        print(f"    [{c:>3}] {j}")
    print(f"\n  OUTPUT FILES")
    print(f"    Candidates:  {output_path}")
    print(f"    CSV:         {csv_path}")
    print(f"    Stats JSON:  {stats_path}")

    logger.info(f"Stage 2 complete: {len(filtered)} candidates")


if __name__ == "__main__":
    main()
