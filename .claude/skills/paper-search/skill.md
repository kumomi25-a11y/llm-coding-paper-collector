---
name: paper-search
description: Search, download, and screen academic papers where LLM/AI is used for text annotation tasks. Supports WoS SSCI or custom journal lists, OpenAlex + Semantic Scholar dual search, PDF download via library proxy, and LLM-based screening.
---

# Paper Search Pipeline

Discover academic papers that **USE LLM/AI as a tool for text annotation** (coding, thematic analysis, content analysis, labeling, extraction) in any discipline. The paper's main topic does NOT need to be about AI — we include papers where AI/LLM is used instrumentally for annotation tasks.

## Quick Start

```
/paper-search --discipline "Public Administration" --years 2023-2026

/paper-search --source custom-list --input journals.csv \
  --proxy "https://lib.ezproxy.xxx.edu/login?url="

/paper-search --discipline "Political Science" \
  --s2-api-key sk-xxx --llm claude
```

## Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `--source` | No | `wos-ssci` | `wos-ssci` or `custom-list` |
| `--discipline` | Yes* | — | WoS SSCI categories, comma-separated (*required for wos-ssci) |
| `--input` | Yes* | — | Journal list file (.csv, .xlsx, .pdf) (*required for custom-list) |
| `--years` | No | `2023-2026` | Publication year range |
| `--s2-api-key` | No | — | Semantic Scholar API key via ai4scholar.net |
| `--proxy` | No | — | Library EZProxy prefix URL |
| `--llm` | No | `deepseek` | Screening LLM: `deepseek`, `claude`, `openai` |
| `--llm-api-key` | No | — | API key for screening LLM |

## Getting a Library Proxy URL

Most university libraries provide EZProxy for off-campus access:
1. Search "[university] library off-campus access ezproxy"
2. Find the EZProxy prefix, usually: `https://lib.ezproxy.{university}.edu/login?url=`
3. Test: paste `{proxy_url}https://doi.org/10.1111/puar.70098` in browser
4. If PDF opens after login → it works

## Pipeline Flow

### Stage 1: Journal Registry
- Auto-runs. Matches journal names/ISSNs to OpenAlex source IDs.
- Shows: journal count, match rate, per-category breakdown.

### Stage 2: Paper Search
- Auto-runs OpenAlex + Semantic Scholar search.
- OpenAlex: free, title+abstract+full-text n-grams, journal-filtered.
- S2: costs API credits, title+abstract, post-filtered to target journals.
- Shows per-keyword hit counts → **ASK USER if they want to prune low-performing S2 keywords** to save costs.

### Stage 3: PDF Download
- Multi-tier: OA direct → Unpaywall → ResearchGate → EZProxy direct PDF.
- **ASK USER before opening visible browser for SSO login.**
- Direct PDF URLs bypass publisher bot checks (no "verify human" pages).
- Generates manual download list for unfetchable papers.

### Stage 4: Text Extraction
- Auto-runs. PyMuPDF4LLM → Markdown, preserving headings and structure.

### Stage 5: LLM Screening
- Sends each paper to screening LLM with classification prompt.
- Classifies: **AS_TOOL** (uses AI for annotation), **AS_METHOD** (studies AI coding), **NOT_FOUND**.
- **ASK USER to review AS_TOOL list and flag any false positives.**

## Review Gates (5 Confirmation Points)

The skill will pause and ask for confirmation at each of these nodes:

1. **After journal matching**: Show matched journals → "Continue to search?"
2. **After paper search**: Show keyword stats → "Prune any S2 keywords before downloading?"
3. **Before download**: "Open visible browser for library SSO login?"
4. **After download**: Show download stats → "Continue to extraction?"
5. **After screening**: Show AS_TOOL list → "Any false positives to exclude?"

## Screening Criteria

```
AS_TOOL (include):  Paper USES LLM/AI to perform annotation tasks
                    (e.g., "We used ChatGPT to code interview transcripts")
                    LLM is a TOOL — paper topic is usually unrelated to AI

AS_METHOD (exclude): Paper STUDIES LLM coding as a method
                     (e.g., "Comparing GPT-4 vs human coders for accuracy")
                     LLM is the OBJECT of study

NOT_FOUND (exclude): No evidence of actual LLM/AI use for annotation
                     (may mention AI in literature review or policy discussion)
```

## Project Location

All pipeline scripts are in `llm-coding-paper-collector/`. See `PIPELINE_DOCUMENTATION.md` for full technical details.
