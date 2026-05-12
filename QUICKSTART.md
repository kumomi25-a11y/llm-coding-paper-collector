# Quick Start Guide

## For First-Time Users

### What This Project Does

Systematically discovers academic papers where **LLM/AI is used as a tool for text annotation** (coding, thematic analysis, content analysis, etc.) in your target discipline. The pipeline searches OpenAlex, downloads PDFs via your library proxy, extracts text, and uses an LLM to screen for relevance.

### Setup (5 minutes)

```bash
# 1. Clone
git clone <repo-url> && cd llm-coding-paper-collector

# 2. Install dependencies
pip install -r requirements.txt
playwright install chromium

# 3. Set your API keys
cp .env.example .env
# Edit .env:
#   DEEPSEEK_API_KEY=sk-xxxxx        (required — for Stage 5 screening)
#   S2_API_KEY=sk-user-xxxxx         (optional — Semantic Scholar)
#   OPENALEX_EMAIL=you@example.com   (required — OpenAlex terms of service)
source .env
```

### Choose Your Path

**If your discipline is NOT Public Administration / Public Policy** (most users):

You need to provide your own journal list. Two options:

*Option A — WoS SSCI (recommended)*:
1. Download `Social Sciences Citation Index (SSCI).csv` from https://mjl.clarivate.com/collection-list-downloads (free registration)
2. Place it in the project root
3. Run: `python scripts/01b_wos_journals.py --categories "Political Science,Sociology"`
4. This builds `data/journals/wos_pa_pp_registry.json` — your journal list

*Option B — Custom list*:
1. Prepare a CSV with columns: `Journal title`, `ISSN`, `eISSN`
2. Edit `scripts/01b_wos_journals.py` to point to your file
3. Or replace `data/journals/pa_journal_registry.json` with your own registry

**If your discipline IS Public Administration / Public Policy**:

The included registries already cover PA/PP journals. Skip to "Run the Pipeline."

### Set Your Library Proxy

If your university provides EZProxy off-campus access:
1. Find the proxy prefix — search "[university] library ezproxy"
2. Common format: `https://lib.ezproxy.{university}.edu/login?url=`
3. Edit `config.yaml`: `ezproxy.base_url: "https://lib.ezproxy.xxx.edu/login?url="`

Without a proxy, only open-access papers can be downloaded.

### Run the Pipeline

```bash
# Stage 1: Journal matching (skip if discipline is PA/PP with included registries)
python scripts/01b_wos_journals.py --categories "Your Discipline"

# Stage 2: Paper search
python scripts/02_search_papers.py

# Stage 3: PDF download
python scripts/03_download_pdfs.py
# If failures, retry with visible browser: python scripts/retry_failed.py

# Stage 4: Text extraction
python scripts/04_extract_text.py

# Stage 5: LLM screening
python scripts/05_screen_papers.py
```

Or run all at once: `python scripts/run_pipeline.py`

### Configuration

Key settings in `config.yaml`:

| Setting | What to change |
|---------|---------------|
| `search.queries` | LLM + method keyword combinations |
| `search.publication_years` | Year range (default: 2023-2026) |
| `ezproxy.base_url` | Your library proxy URL |
| `ezproxy.headless` | Set to `false` for SSO login |
| `pipeline.max_papers_to_download` | Cap on downloads |
| `semantic_scholar.enabled` | Toggle S2 search |
| `openalex.email` | Your email (required by OpenAlex) |

### Output Files

| File | Content |
|------|---------|
| `data/screening_results.md` | Human-readable screening table |
| `data/screening_results_v2.jsonl` | Final screening verdicts (v2 strict) |
| `data/final_corpus.md` | Final paper list with evidence and file paths |
| `output/screening_comparison.csv` | v2 vs v3 side-by-side comparison |
| `output/search_stats.json` | Per-keyword hit statistics |
| `PIPELINE_DOCUMENTATION.md` | Full pipeline documentation |

### Included Data (for PA/PP discipline)

The repo includes pre-built registries for Public Administration & Public Policy:
- `data/journals/pa_journal_registry.json` — 79 PA journals matched to OpenAlex
- `data/journals/pa_journals_all.json` — Canonical PA journal names
- `data/journals/wos_pa_pp_registry.json` — 341 SSCI journals (PA + adjacent fields)
- `Social Sciences Citation Index (SSCI).csv` — WoS master journal list
- `journal_list_pa.pdf` — JCR 2025 PA category PDF

**Users in other disciplines**: replace or supplement these with your own lists.

### Troubleshooting

*"No PDFs downloaded"* — Your library proxy URL is likely wrong or not set. OA papers should still work. Check `output/download_stats.json`.

*"All S2 queries returned 0"* — S2's snippet/search doesn't support complex OR-logic queries. Use simple keyword pairs or disable S2.

*"SSO login not working"* — Set `ezproxy.headless: false` in config.yaml, run `retry_failed.py`, and complete login in the visible browser window.

*"DeepSeek API key not found"* — Make sure `source .env` was run and `DEEPSEEK_API_KEY` is set.
