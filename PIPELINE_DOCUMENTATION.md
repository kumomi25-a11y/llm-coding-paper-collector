# LLM Coding Paper Collector — Pipeline Documentation

## Overview

### Purpose

This pipeline systematically discovers academic papers where **LLM/AI is used as a tool for text annotation** — any task traditionally performed by human coders that is partially or fully delegated to machine/AI/LLM. This includes coding qualitative data, thematic analysis, content analysis, text labeling, information extraction, and similar annotation workflows.

**Key design principle**: The paper's main topic does NOT need to be about AI/LLM. A public administration paper that uses ChatGPT to code interview transcripts is in-scope. A paper comparing GPT-4's coding accuracy to humans is out-of-scope (that paper studies LLM as a method, not as a tool).

### Scope

- **Disciplines**: Public Administration & Public Policy (pilot), scalable to all WoS SSCI categories
- **Journal sources**: JCR 2025 PDF (89 PA journals, pilot run) with WoS SSCI CSV (341 journals) verified for future scale-up
- **Publication years**: 2023–2026
- **Search sources**: OpenAlex (full-text n-grams) + Semantic Scholar (title+abstract, via ai4scholar.net proxy)

### Pipeline Architecture

```
Stage 1              Stage 2              Stage 3              Stage 4           Stage 5
┌──────────┐        ┌──────────┐         ┌──────────┐         ┌──────────┐      ┌──────────┐
│ Journal  │─JSON─→ │  Paper   │─JSONL─→ │   PDF    │──.md─→  │  Text    │─md─→ │   LLM    │
│ Registry │        │  Search  │         │ Download │         │ Extract  │      │  Screen  │
└──────────┘        └──────────┘         └──────────┘         └──────────┘      └──────────┘
  1a: JCR PDF           OpenAlex            Tier 1: OA          pymupdf4llm        DeepSeek V3
  1b: WoS SSCI          dedup by DOI        Tier 2: Unpaywall    fitz fallback      AS_TOOL|METHOD
   ISSN → OA ID         175 candidates      Tier 3: EZProxy                         19 papers final
                                           170/175 PDFs        170 .md files
```

### Final Results (2026-05-12 run)

| Stage | Input | Output | Notes |
|-------|-------|--------|-------|
| **1a. JCR Registry** | 89 PA journals (PDF) | 77 matched | 12 non-English not found |
| **1b. WoS SSCI Registry** | 343 SSCI journals (CSV) | 341 matched | PA+PolSci+Social Issues+Health Policy. +2 English SSCI PA journals added to search registry (Canadian Public Admin/Policy). |
| **2. Paper Search** | 79 PA journals (76 unique source IDs), 5 OA queries, 5 S2 snippet queries | **175 candidates** | 175 OA. S2 snippet/search returned 0 (complex OR queries unsupported). Total search scope: JCR PA + 2 SSCI additions. |
| **3. PDF Download** | 175 candidates | **170 PDFs** | 97.1% success. 5 unfetchable (no library subscription or OA server issues). |
| **4. Text Extraction** | 170 PDFs | **170 .md files** | 1.70M words, avg 10,026/paper. 100% extraction success. |
| **5. LLM Screening** | 170 papers (DeepSeek V3, 4 concurrent) | **19 AS_TOOL (final)** | v2 strict prompt chosen over v3 inclusive (64 AS_TOOL, too many false positives). V4 Pro attempted but thinking mode caused JSON parsing failures; reverted to V3. See `data/final_corpus.md`. |

---

## Stage 1: Journal Registry

### Purpose

Build a mapping from target journal names → OpenAlex Source IDs. The Source ID is required for Stage 2's venue-filtered search.

### Two Paths

**Path A — JCR PDF (pilot, PA only)**: Reads the 89-journal list extracted from Journal Citation Reports 2025 PDF. Matches by fuzzy journal name against OpenAlex `/sources` endpoint.

**Path B — WoS SSCI (scalable, all disciplines)**: Reads `Social Sciences Citation Index (SSCI).csv` downloaded from [Clarivate MJL](https://mjl.clarivate.com/collection-list-downloads). Filters by WoS Categories, matches by **ISSN** (more reliable than name matching).

### Scripts

```bash
python scripts/01_fetch_q1_journals.py          # Path A: JCR PDF
python scripts/01b_wos_journals.py               # Path B: WoS SSCI
python scripts/01b_wos_journals.py \
  --categories "Political Science,Sociology"      # Custom categories
```

### Core Logic (WoS Path)

```python
# Parse WoS SSCI CSV, filter by categories
wos_journals = parse_wos_csv(csv_path, categories=["Public Administration", "Political Science"])

# Match to OpenAlex by ISSN (exact)
for journal in wos_journals:
    resp = oa_client._get("/sources", params={"filter": f"issn:{journal['issn']}"})
    source = resp["results"][0]
    registry.append({
        "openalex_source_id": source["id"].split("/")[-1],
        "openalex_issn_l": source["issn_l"],
        "wos_categories": journal["categories"],
    })
```

### Key Design Decision: ISSN over Name Matching

WoS SSCI provides exact ISSN, which matches OpenAlex precisely. JCR PDF only provides journal names, requiring fuzzy matching. ISSN matching yields 341/343 (99.4%) vs name matching 77/89 (86.5%).

### Dual-Path Verification

| | JCR PDF | WoS SSCI |
|---|---|---|
| Source | 89 PA journals (Q1-Q4, JCR 2025) | 343 journals (SSCI-indexed only) |
| Match method | Fuzzy name | Exact ISSN |
| Match rate | 77/89 (86.5%) | 341/343 (99.4%) |
| Overlap | 38 journals (core PA in SSCI) | |
| JCR only | 35 journals (ESCI, not SSCI, e.g. Lex localis) | |
| WoS only | — | 303 journals (PolSci, Health Policy, Social Issues) |

---

## Stage 2: Paper Search

### Purpose

Search for papers mentioning LLM/AI + annotation method terms, within target PA journals.

### Dual-Source Strategy

| Source | What it searches | Strength | Limitation |
|--------|-----------------|----------|------------|
| **OpenAlex** | Title + abstract + full-text n-grams | Free, journal-filtered at query time | N-grams may miss rare phrases |
| **Semantic Scholar** (ai4scholar.net) | Full-text `snippet/search` | True full-text search, not just n-grams | Complex OR-logic queries return 0 results; requires simple phrase queries. Not used in final run. |

### Search Queries (config.yaml)

```
Q1: "LLM" OR "LLMs" OR "large language model" OR "ChatGPT" OR "GPT-4" ...
    AND ("coding" OR "annotation" OR "thematic analysis" OR ...)

Q2: "Claude" OR "Claude AI" OR "Anthropic Claude" ...

Q3: "Gemini" OR "DeepSeek" OR "LLaMA" OR "Mistral" OR "Copilot" ...

Q4: "generative AI" OR "GenAI" OR "generative artificial intelligence" ...

Q5: "AI-assisted" OR "AI-powered" OR "NLP" OR "natural language processing" ...
```

### S2 Keyword Pruning

S2 costs API credits. Per-query stats are saved to `output/search_stats.json`. Low-performing keywords (e.g. "NLP coding" → 0 PA hits) can be removed from `_derive_s2_keywords()` in `scripts/02_search_papers.py`.

### Critical Bug Fix: 50 Source-ID Limit

OpenAlex's filter supports max 50 OR'd source IDs. Initial code only used `source_ids[:50]`, silently skipping 27 journals. **Fix**: chunk source IDs into batches of 50, search each batch separately, merge results.

```python
# Before (BUG): only first 50 journals searched
id_chunk = source_ids[:50]

# After (FIX): all journals searched in batches
for i in range(0, len(source_ids), 50):
    batch = source_ids[i:i+50]
    # search with this batch, merge results
```

### Journal Filter Bug Fix

Empty journal name (`""`) matched all PA journal names via Python's `"" in "string"` → `True`. This let 94 arXiv/non-PA papers leak through. **Fix**: require non-empty name before fuzzy matching.

### S2 DOI Enrichment

S2 paper/search often returns papers without journal metadata. Before journal filtering, each S2 paper is enriched via OpenAlex DOI lookup:

```python
# For S2 papers lacking journal info:
oa_meta = oa_client.get_work_by_doi(s2_paper["doi"])
if oa_meta:
    s2_paper["journal"] = oa_meta["journal"]
    s2_paper["journal_issn_l"] = oa_meta["journal_issn_l"]
```

### Final Run Metrics

```
OA queries:             5 (from config.yaml)
OA raw hits:            189 (across 76 source IDs in 2 batches)
S2 snippet queries:     5 (all returned 0 — complex OR unsupported)
After dedup by DOI:     175 unique
After journal filter:   175 in PA journals (100% pass-through, all OA-sourced)
Final candidates:       175 papers from 79 PA journals
```

---

## Stage 3: PDF Download

### Purpose

Download PDFs for all 181 candidates, maximizing success rate through a multi-tier strategy.

### Download Strategy (4 tiers)

```
Tier 1: OA Direct HTTP
  → Try oa_url from OpenAlex metadata
  → Works for truly OA papers

Tier 2: Unpaywall API
  → Find alternative OA copies via unpaywall.org
  → Requires email in config

Tier 3: ResearchGate
  → Search researchgate.net for author-uploaded preprints

Tier 4: EZProxy Direct PDF URLs (KEY INNOVATION)
  → Bypass publisher landing pages entirely
  → Direct PDF URL patterns per publisher:
    Wiley:    /doi/pdfdirect/{doi}?download=true
    Sage:     /doi/pdf/{doi}?download=true
    Oxford:   /documentlibrary/doi/pdfdirect/{doi}
    Springer: /content/pdf/{doi}.pdf
    Cambridge:/core/services/aop-cambridge-core/content/view/{doi}
    Emerald:  /insight/content/doi/{doi}/full/pdf
    Elsevier: /science/article/pii/{pii}/pdfft
    T&F:      /doi/pdf/{doi}?download=true
    MDPI:     mdpi-res.com CDN
  → Prefixed with EZProxy: https://lib.ezproxy.hkust.edu.hk/login?url={pdf_url}
  → Downloaded via requests.Session with SSO cookies (NOT Playwright)
```

### EZProxy Automation Strategy

**Problem**: Publisher landing pages detect Playwright as a bot → "verify you are human" → download fails.

**Solution**: Two-phase approach:
1. **Playwright for SSO only**: Open visible browser once, user completes SSO+Duo login. Extract cookies.
2. **HTTP for all downloads**: Use `requests.Session` with extracted cookies. Direct PDF URLs bypass landing pages entirely → no bot detection.

```python
# Phase 1: Extract cookies from Playwright SSO session
page.goto("https://lib.ezproxy.hkust.edu.hk/login?url=https://onlinelibrary.wiley.com/doi/pdfdirect/10.1111/puar.70098")
# User logs in → cookies saved to Playwright profile

# Phase 2: Use cookies in requests.Session
pw_cookies = browser_context.cookies()
for c in pw_cookies:
    session.cookies.set(c["name"], c["value"], domain=".hkust.edu.hk")

# Download via HTTP (no bot detection)
resp = session.get(f"{ezproxy_base}{direct_pdf_url}")
```

### Download Results

| Method | Count | Notes |
|--------|-------|-------|
| oa_direct + cached | 168 | OA papers (mostly cached from prior runs) |
| ezproxy | 2 | Via EZProxy direct PDF (Wiley) |
| Failed | 5 | 4 unsubscribed journals + 1 OA server unreachable |

### Retry Failed Downloads

```bash
python scripts/retry_failed.py    # Opens visible browser, SSO login, retries all failed
```

---

## Stage 4: Text Extraction

### Purpose

Extract clean, structured Markdown from PDFs for downstream LLM screening.

### Library Choice

**PyMuPDF4LLM** (primary): Preserves document structure as Markdown (headings, paragraphs, tables). Essential for LLM screening — the model can locate methods sections by heading structure.

**Fitz plain text** (fallback): Used when pymupdf4llm produces fewer than 500 words.

```python
# Primary
md_text = pymupdf4llm.to_markdown(pdf_path, write_images=False)

# Fallback
doc = fitz.open(pdf_path)
text = "\n".join(page.get_text() for page in doc)
```

### Results

| Metric | Value |
|--------|-------|
| PDFs processed | 170 |
| Extracted | 170 (100%) |
| Total words | 1,704,447 |
| Average words/paper | 10,026 |
| Median words/paper | 10,366 |
| Range | 2,396 – 20,043 |

---

## Stage 5: LLM Screening

### Purpose

Distinguish papers that **USE** LLM/AI as a tool for annotation from those that merely mention it.

### Screening Criteria

**AS_TOOL (include)**: Paper uses LLM/AI to perform annotation tasks traditionally done by humans.
- Example: "We used ChatGPT to code interview transcripts"
- Example: "GPT-4 was employed to generate labels for topic modeling"
- The LLM use may be brief, in any section (methods, results, footnotes, acknowledgments)
- The paper's main topic is usually **unrelated to AI**

**AS_METHOD (exclude)**: Paper studies or evaluates LLM coding as a method.
- Example: "Comparing GPT-4 and human coders for thematic analysis accuracy"
- The LLM is the **object of study**, not a tool

**NOT_FOUND (exclude)**: No evidence of actual LLM/AI use for annotation.
- May mention AI/LLM in literature review, policy discussion, or future directions
- But does not describe using it for annotation

### Prompt Design

The full screening prompt sent to DeepSeek:

```
You are screening academic papers to identify those that USE large 
language models (LLMs) or AI as a TOOL for text annotation tasks.

## Classification

Read the paper and classify it into ONE of three categories:

**AS_TOOL** — The paper USES LLM/AI to perform annotation/coding tasks.
- The LLM is a TOOL, not the object of study
- Even a brief mention of using AI/LLM for coding/annotation counts
- The usage may appear in methods, results, discussion, footnotes, anywhere

**AS_METHOD** — The paper STUDIES or EVALUATES LLM/AI coding methods.
- The LLM is the OBJECT of study, not a tool
- Paper compares models, tests accuracy, designs prompts

**NOT_FOUND** — No evidence of using or studying LLM/AI for text annotation.

## IMPORTANT: Err on the side of AS_TOOL if there is any reasonable 
indication. A paper about public policy that uses ChatGPT to analyze 
documents IS AS_TOOL.

## Output Format (JSON only):
{
  "verdict": "AS_TOOL",
  "confidence": 1-5,
  "evidence": "quote from paper",
  "task": "coding|thematic analysis|content analysis|labeling|extraction|other",
  "section": "Methods"
}
```

### Model Choice

**DeepSeek V4 Pro** (`deepseek-v4-pro`) via API. Key considerations:
- 64K context window fits most papers (median 10K words)
- JSON mode (`response_format: {"type": "json_object"}`) ensures parseable output
- Current run used DeepSeek V3 (`deepseek-chat`); future runs will use V4 Pro (`deepseek-v4-pro`)
- Cost: ~$2.50 for 176 papers (V3 pricing)

### Results

Two screening runs were performed with different prompt strictness:

| Run | Prompt | AS_TOOL | Notes |
|-----|--------|---------|-------|
| v2 (strict) | Err on side of AS_TOOL | **19 (11%)** | Higher precision, chosen as final |
| v3 (inclusive) | Additional NLP/ML inclusion directive | 64 (38%) | Higher recall, too many false positives |

**Final selection: v2 (19 papers).**

The v3 inclusive prompt added "If the paper used ANY automated method for text analysis (NLP, ML, topic modeling, sentiment analysis, named entity recognition, text classification), mark AS_TOOL." This captured many papers that use NLP/ML for prediction or classification tasks unrelated to text annotation (e.g., sentiment analysis for customer feedback, AI courtroom simulations, deep learning for spatial analysis). These are not within scope — they use AI as a computational tool, not to replace human text annotation work.

The v2 strict prompt better isolates papers where LLM/AI specifically replaces human coding/annotation/analysis of textual data — which is the core research interest.

### Final Corpus (19 AS_TOOL papers)

See `data/final_corpus.md` for the complete list with evidence, task labels, and file paths.

### Task Breakdown (19 papers)

| Task | Count |
|------|-------|
| Content analysis | 4 |
| Coding | 3 |
| Classification | 2 |
| Extraction | 2 |
| Topic modeling | 2 |
| Thematic analysis | 1 |
| Sentiment analysis | 1 |
| Named entity recognition | 1 |
| Other | 3 |

---

## Key Technical Decisions

### Why OpenAlex AND Semantic Scholar?

OpenAlex searches full-text n-grams (key phrases from PDFs), covering ~85-90% of relevant text. S2 `snippet/search` offers true full-text search. However, S2's snippet endpoint does not support complex OR-logic queries — all 5 config.yaml queries returned 0 results. S2 `paper/search` (title+abstract) can complement OA with simple keyword pairs, but was not used in the final run. **S2 remains available as an optional complement if simple queries are used.**

### Why Direct PDF URLs?

Publisher landing pages (Wiley, Sage, Oxford) use Cloudflare/PerimeterX bot detection. Playwright-based navigation triggers "verify you are human" pages. Direct PDF URLs (e.g., Wiley's `/doi/pdfdirect/`) serve PDFs directly without loading the landing page → no bot checks.

### Why Cookie-Based HTTP over Playwright?

Once EZProxy SSO cookies are extracted from Playwright's browser context, all subsequent downloads use `requests.Session`. This is:
- **Faster**: HTTP requests complete in 1-2s vs 10-15s for page navigation
- **More reliable**: No bot detection, no JavaScript rendering
- **Cheaper**: Lower memory/CPU usage

### Why Two-Layer Screening?

Using AS_TOOL vs AS_METHOD separation prevents false inclusions. Without this distinction, papers studying LLM coding methodology would be incorrectly included. The key insight: **"We used ChatGPT to code" ≠ "We studied whether ChatGPT codes well."**

---

## Claude Code Skill

### Installation

The skill is at `~/.claude/skills/paper-search/skill.md`.

### Usage

```
/paper-search --discipline "Public Administration" --years 2023-2026

/paper-search --source custom-list --input journals.csv \
  --proxy "https://lib.ezproxy.xxx.edu/login?url=" \
  --s2-api-key sk-xxx

/paper-search --discipline "Political Science,Sociology" \
  --years 2020-2026 --s2-api-key sk-xxx
```

### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `--source` | No | `wos-ssci` (default) or `custom-list` |
| `--discipline` | For wos-ssci | WoS SSCI categories, comma-separated |
| `--input` | For custom-list | Path to journal list (.csv, .xlsx, .pdf) |
| `--years` | No | Publication year range (default: 2023-2026) |
| `--s2-api-key` | No | Semantic Scholar API key for full-text search |
| `--proxy` | No | Library EZProxy prefix URL |
| `--llm` | No | Screening LLM choice (deepseek, claude, openai) |
| `--llm-api-key` | No | API key for screening LLM |

### How to Get Your Library Proxy URL

1. Find your university library's "off-campus access" or "EZProxy" page
2. Common format: `https://lib.ezproxy.{university}.edu/login?url=`
3. Test: paste `{proxy_url}https://doi.org/10.1111/puar.70098` in browser
4. If it opens a PDF after SSO login, the proxy works

### Skill Interaction Flow

1. Skill asks for: discipline, years, proxy URL, S2 API key (optional), screening LLM (optional)
2. **Stage 1**: Auto-runs journal matching. Shows journal count + OpenAlex match rate.
3. **Stage 2**: Auto-runs paper search. Shows per-keyword hit stats, asks if user wants to prune S2 keywords.
4. **Stage 3**: If proxy provided, opens visible browser for SSO login. Downloads PDFs. Shows method breakdown. Generates manual download list for failures.
5. **Stage 4**: Auto-runs text extraction. Shows word count stats.
6. **Stage 5**: Auto-runs LLM screening. Shows verdict breakdown. User reviews AS_TOOL list and can flag false positives.

### Key Confirmation Points (Review Gates)

The skill pauses for user confirmation at these nodes:

1. **After journal matching**: "X journals matched. Continue to search?"
2. **After paper search**: "X candidates found. Review keyword stats? Prune S2 keywords?"
3. **Before SSO login**: "Opening visible browser for library login. Ready?"
4. **After download**: "X PDFs downloaded. Review failures? Continue to extraction?"
5. **After screening**: "X AS_TOOL papers found. Review list? Any false positives to exclude?"

---

## Project Structure

```
llm-coding-paper-collector/
    config.yaml                     # Central configuration
    requirements.txt                # Python dependencies
    PIPELINE_DOCUMENTATION.md       # This file
    Social Sciences Citation Index (SSCI).csv  # WoS journal list

    scripts/
        01_fetch_q1_journals.py    # Stage 1a: JCR PDF path
        01b_wos_journals.py         # Stage 1b: WoS SSCI path
        02_search_papers.py         # Stage 2: OA + S2 search
        03_download_pdfs.py         # Stage 3: PDF download
        04_extract_text.py          # Stage 4: Text extraction
        05_screen_papers.py         # Stage 5: LLM screening
        retry_failed.py             # Retry failed downloads
        run_pipeline.py             # Run all stages

    utils/
        openalex_client.py          # OpenAlex API (source lookup, works search, DOI enrichment)
        semantic_scholar_client.py  # S2 API via ai4scholar.net
        ezproxy_downloader.py       # Multi-tier PDF downloader
        pdf_extractor.py            # PyMuPDF4LLM + fitz fallback
        rate_limiter.py             # Token bucket rate limiter
        config_loader.py            # Config loader with ${ENV_VAR} expansion
        logger.py                   # Dual console+file logger

    data/
        journals/                   # Journal registries (JCR + WoS SSCI)
        search_results/             # Candidates, download logs
        pdfs/                       # Downloaded PDFs (170 files)
        extracted_text/             # Extracted markdown (170 files)
        screening_results.jsonl     # Full screening verdicts (170 papers)
        screening_results_v2.jsonl  # v2 strict screening (19 AS_TOOL — FINAL)
        screening_results_v3.jsonl  # v3 inclusive screening (64 AS_TOOL)
        screening_results.md        # Human-readable screening report
        final_corpus.md             # Final 19 papers with evidence, task, file paths
        final_corpus.json           # Final corpus in JSON format

    output/
        search_stats.json           # Per-keyword hit stats
        download_stats.json         # Download method breakdown
        extraction_stats.json       # Text extraction stats
        screening_comparison.csv    # v2 vs v3 side-by-side comparison
        manual_download_final.txt   # Unfetchable DOIs
```

## References

- OpenAlex: Priem, J., Piwowar, H., & Orr, R. (2022). OpenAlex: A fully-open index of scholarly works. *arXiv:2205.01833*
- PyMuPDF4LLM: Artifex Software. https://pymupdf.readthedocs.io/
- Semantic Scholar API: https://api.semanticscholar.org/
- ai4scholar.net: S2 API proxy with API key authentication
- WoS Master Journal List: https://mjl.clarivate.com/
