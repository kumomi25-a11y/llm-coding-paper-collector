#!/usr/bin/env python3
"""
Stage 5: LLM Screening — classify each paper as AS_METHOD / AS_TOOL / NOT_FOUND.

Reads extracted .md files, sends to DeepSeek API, records verdicts.

Usage:
    python scripts/05_screen_papers.py
    python scripts/05_screen_papers.py --start 0 --end 50   # batch range
    python scripts/05_screen_papers.py --resume              # skip already screened

Output: data/screening_results.jsonl + data/screening_results.md
"""

import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.config_loader import load_config
from utils.logger import setup_logging

logger = logging.getLogger("paper_collector")

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
if not DEEPSEEK_API_KEY:
    print("ERROR: DEEPSEEK_API_KEY not set. Run: export DEEPSEEK_API_KEY=sk-xxxxx")
    sys.exit(1)
MODEL = "deepseek-chat"  # V3 — more stable JSON output than V4 Pro with reasoning
MAX_TOKENS_PER_REQUEST = 50000  # Conservative estimate for 64K context

SCREENING_PROMPT = """You are screening academic papers to identify those that USE large language models (LLMs) or AI as a TOOL for text annotation tasks.

## Classification

Read the paper and classify it into ONE of three categories:

**AS_TOOL** — The paper USES LLM/AI to perform annotation/coding tasks.
- The LLM is a TOOL, not the object of study
- Examples: using ChatGPT to code interview transcripts, using LLM for thematic analysis of policy documents, using AI to label survey responses
- The paper's main topic is likely UNRELATED to AI (e.g., public administration, political science, social policy)
- Even a brief mention of using AI/LLM for coding/annotation counts
- The usage may appear in methods, results, discussion, footnotes, or anywhere

**AS_METHOD** — The paper STUDIES or EVALUATES LLM/AI coding methods.
- The LLM is the OBJECT of study, not a tool
- Examples: comparing GPT-4 vs human coders, testing annotation accuracy, designing coding prompts, evaluating LLM coding quality
- The paper's main topic IS about LLM/AI methodology

**NOT_FOUND** — No evidence of using or studying LLM/AI for text annotation.
- The paper may mention AI/LLM only in literature review, future directions, or general policy discussion
- No actual use of AI/LLM for annotation tasks described

## CRITICAL: When in doubt between AS_TOOL and NOT_FOUND, choose AS_TOOL.
## Our priority is to NOT miss any genuine cases. False positives are acceptable.
## Even a single sentence mentioning AI-assisted coding/annotation counts.
## If the paper used ANY automated method for text analysis (NLP, ML, topic modeling,
## sentiment analysis, named entity recognition, text classification), mark AS_TOOL.
## A paper about public policy that uses ChatGPT to analyze documents IS AS_TOOL.
## A paper comparing GPT-4's coding accuracy to humans IS AS_METHOD.
## Only mark NOT_FOUND if there is truly zero evidence of AI/NLP/ML use for text work.

## Output Format
Return ONLY a JSON object, no other text:
{
  "verdict": "AS_TOOL",
  "confidence": 4,
  "evidence": "We used ChatGPT-4 to perform thematic analysis on the interview transcripts...",
  "task": "thematic analysis",
  "section": "Methods"
}

Confidence: 1 (very uncertain) to 5 (completely certain).
Task: coding / thematic analysis / content analysis / labeling / extraction / other.
Section: where in the paper the evidence was found."""


def count_tokens(text: str) -> int:
    """Rough token count: ~4 chars per token for English text."""
    return len(text) // 4


def truncate_text(text: str, max_tokens: int) -> str:
    """Truncate text to fit within token budget, keeping beginning and end."""
    max_chars = max_tokens * 4
    if len(text) <= max_chars:
        return text
    # Keep first 60% + last 20%
    head_chars = int(max_chars * 0.75)
    tail_chars = int(max_chars * 0.20)
    return text[:head_chars] + "\n\n[... truncated ...]\n\n" + text[-tail_chars:]


def screen_paper(text: str, title: str = "", session: requests.Session = None) -> dict:
    """Send paper text to DeepSeek for screening. Returns parsed verdict dict."""
    if session is None:
        session = requests.Session()

    # Truncate if needed
    prompt_chars = len(SCREENING_PROMPT) // 4
    available = MAX_TOKENS_PER_REQUEST - prompt_chars - 500  # 500 for response
    truncated = truncate_text(text, available)

    messages = [
        {"role": "system", "content": SCREENING_PROMPT},
        {"role": "user", "content": f"Title: {title}\n\nPaper text:\n\n{truncated}"},
    ]

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": 800,
        "temperature": 0.0,
        "response_format": {"type": "json_object"},
    }

    for attempt in range(3):
        try:
            resp = session.post(DEEPSEEK_URL, headers=headers, json=payload, timeout=120)
            if resp.status_code == 429:
                wait = min(2 ** attempt * 5, 30)
                logger.warning(f"DeepSeek rate limit, waiting {wait}s...")
                time.sleep(wait)
                continue
            resp.raise_for_status()

            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})

            # Parse JSON from response
            try:
                # Strip markdown code fences if present
                content = content.strip()
                if content.startswith("```"):
                    content = content.split("\n", 1)[1]
                    if content.endswith("```"):
                        content = content[:-3]
                result = json.loads(content)
                result["_tokens_in"] = usage.get("prompt_tokens", 0)
                result["_tokens_out"] = usage.get("completion_tokens", 0)
                return result
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse DeepSeek response: {content[:200]}")
                # Retry with simpler prompt
                if attempt == 2:
                    return {"verdict": "PARSE_ERROR", "confidence": 0, "evidence": content[:200], "task": "", "section": ""}

        except Exception as e:
            logger.warning(f"DeepSeek API error (attempt {attempt+1}): {e}")
            if attempt < 2:
                time.sleep(5)

    return {"verdict": "API_ERROR", "confidence": 0, "evidence": "", "task": "", "section": ""}


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--end", type=int, default=None)
    parser.add_argument("--resume", action="store_true", help="Skip already screened papers")
    args = parser.parse_args()

    config = load_config()
    setup_logging(config)

    logger.info("=" * 60)
    logger.info("Stage 5: LLM Screening (DeepSeek)")
    logger.info("=" * 60)

    # Load candidates
    candidates_path = Path("data/search_results/deduplicated_candidates.jsonl")
    with open(candidates_path) as f:
        candidates = {json.loads(line)["doi"]: json.loads(line) for line in f if line.strip()}

    # Load existing results for resume
    screened_dois = set()
    results_path = Path("data/screening_results.jsonl")
    existing_results = []
    if args.resume and results_path.exists():
        with open(results_path) as f:
            for line in f:
                if line.strip():
                    r = json.loads(line)
                    screened_dois.add(r.get("doi", ""))
                    existing_results.append(r)
        logger.info(f"Resuming: {len(screened_dois)} already screened")

    # Find PDFs with extracted text
    text_dir = Path("data/extracted_text")
    md_files = {p.stem: p for p in text_dir.glob("*.md")}

    # Match to candidates
    todo = []
    for doi, c in candidates.items():
        doi_safe = doi.replace("/", "_").replace(":", "_").replace(".", "_")
        if doi in screened_dois:
            continue
        if doi_safe in md_files:
            todo.append((doi, c, md_files[doi_safe]))

    if args.end:
        todo = todo[args.start:args.end]
    elif args.start:
        todo = todo[args.start:]

    logger.info(f"Papers to screen: {len(todo)}")
    logger.info(f"Model: {MODEL}")
    logger.info(f"Workers: 4 (concurrent)")

    results = existing_results.copy()
    total_tokens_in = 0
    total_tokens_out = 0
    results_lock = Lock()
    tokens_lock = Lock()

    def screen_one(idx, doi, c, md_path):
        title = c.get("title", "?")
        journal = c.get("journal", "?")
        try:
            text = md_path.read_text(encoding="utf-8")
        except Exception:
            text = md_path.read_text(encoding="latin-1")
        word_count = len(text.split())

        session = requests.Session()
        result = screen_paper(text, title, session)
        result["doi"] = doi
        result["title"] = title
        result["journal"] = journal
        result["word_count"] = word_count

        ti = result.pop("_tokens_in", 0)
        to = result.pop("_tokens_out", 0)

        with tokens_lock:
            nonlocal total_tokens_in, total_tokens_out
            total_tokens_in += ti
            total_tokens_out += to

        logger.info(f"[{idx+1}/{len(todo)}] {title[:80]}... → {result.get('verdict','?')} (c={result.get('confidence',0)})")

        return result

    completed = len(existing_results)
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(screen_one, i, doi, c, mp): i for i, (doi, c, mp) in enumerate(todo)}
        for future in as_completed(futures):
            result = future.result()
            with results_lock:
                results.append(result)
                completed += 1
                # Save incrementally
                with open(results_path, "w") as f:
                    for r in results:
                        f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # ---- Summary ----
    verdict_counts = {}
    for r in results:
        v = r.get("verdict", "?")
        verdict_counts[v] = verdict_counts.get(v, 0) + 1

    print(f"\n{'='*60}")
    print(f"STAGE 5: Screening Complete")
    print(f"{'='*60}")
    print(f"  Total screened:      {len(results)}")
    print(f"  Total tokens:        {total_tokens_in:,} in + {total_tokens_out:,} out")
    print(f"\n  VERDICTS:")
    for v, c in sorted(verdict_counts.items(), key=lambda x: -x[1]):
        pct = 100 * c / len(results)
        print(f"    {v:<20} {c:>4} ({pct:.1f}%)")

    # Save markdown table
    md_path = Path("data/screening_results.md")
    with open(md_path, "w") as f:
        f.write("# LLM Paper Screening Results\n\n")
        f.write(f"**Screened**: {len(results)} papers | **Date**: {time.strftime('%Y-%m-%d')}\n\n")
        f.write("| # | Verdict | Conf | Task | Year | Title | Journal |\n")
        f.write("|---|---------|------|------|------|-------|--------|\n")
        for i, r in enumerate(results):
            v = r.get("verdict", "?")
            c = r.get("confidence", 0)
            task = (r.get("task") or "")[:20]
            year = r.get("publication_year", r.get("year", "?"))
            title = (r.get("title", "") or "")[:70]
            journal = (r.get("journal", "") or "")[:30]
            f.write(f"| {i+1} | {v} | {c} | {task} | {year} | {title} | {journal} |\n")

    print(f"\n  Saved: {results_path}")
    print(f"  Saved: {md_path}")


if __name__ == "__main__":
    main()
