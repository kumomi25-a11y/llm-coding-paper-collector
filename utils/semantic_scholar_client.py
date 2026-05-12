"""Semantic Scholar API client via ai4scholar.net proxy.

Auth: Authorization: Bearer <api_key>
Rate: 5 req/s with API key, 0.25 req/s without.
"""

import logging
import time
from typing import Optional

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from utils.rate_limiter import RateLimiter

logger = logging.getLogger("paper_collector")

BASE_URL = "https://ai4scholar.net/graph/v1"


class SemanticScholarClient:
    def __init__(self, api_key: Optional[str] = None, max_results: int = 1000):
        self.api_key = api_key
        self.max_results = max_results
        self.session = requests.Session()
        if api_key:
            self.session.headers["Authorization"] = f"Bearer {api_key}"
            self.rate_limiter = RateLimiter(calls_per_second=5, burst=10)
        else:
            self.rate_limiter = RateLimiter(calls_per_second=0.25, burst=1)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, max=30))
    def _get(self, url: str, params: dict = None) -> dict:
        self.rate_limiter.acquire()
        resp = self.session.get(url, params=params or {}, timeout=30)
        if resp.status_code == 429:
            logger.warning("S2 rate limit (429), backing off")
            raise Exception("429")
        if resp.status_code == 403:
            logger.error(f"S2 auth failed (403) — check API key")
            raise Exception("403")
        resp.raise_for_status()
        return resp.json()

    def snippet_search(self, query: str) -> list[dict]:
        """
        Search full-text snippets for the given query.
        This searches the actual full text of papers (not just n-grams).
        """
        all_hits = []
        url = f"{BASE_URL}/snippet/search"
        params = {"query": query, "limit": min(self.max_results, 1000)}

        try:
            data = self._get(url, params)
        except Exception as e:
            logger.warning(f"S2 snippet search failed for '{query[:60]}...': {e}")
            return []

        # ai4scholar returns "data", official S2 returns "hits"
        hits = data.get("data", data.get("hits", []))
        for hit in hits:
            paper = hit.get("paper", {})
            external_ids = paper.get("externalIds") or {}
            doi = external_ids.get("DOI") or external_ids.get("doi")
            if not doi:
                continue

            snippet_info = hit.get("snippet", {})
            snippet_text = snippet_info.get("text", "") if isinstance(snippet_info, dict) else str(snippet_info)

            all_hits.append({
                "doi": doi,
                "title": paper.get("title"),
                "publication_year": paper.get("year"),
                "authors": [{"name": a if isinstance(a, str) else a.get("name", "")} for a in (paper.get("authors") or [])],
                "journal": paper.get("journal", {}).get("name") if isinstance(paper.get("journal"), dict) else paper.get("journal"),
                "s2_snippet": snippet_text,
                "s2_corpus_id": paper.get("corpusId") or paper.get("paperId"),
                "s2_source_section": snippet_info.get("section") if isinstance(snippet_info, dict) else "",
                "source": "semantic_scholar",
            })

        logger.info(f"S2 snippet search '{query[:50]}...' → {len(all_hits)} unique DOIs")
        return all_hits

    def search_papers(self, query: str, year_start: int = 2024) -> list[dict]:
        """Keyword search in title + abstract via ai4scholar paper/search."""
        all_papers = []
        url = f"{BASE_URL}/paper/search"
        params = {
            "query": query,
            "publicationDateOrYear": f"{year_start}:",
            "limit": min(self.max_results, 100),
            "fields": "paperId,title,year,authors,externalIds,journal,openAccessPdf,abstract,citationCount",
        }

        for offset in range(0, min(self.max_results, 1000), 100):
            params["offset"] = offset
            try:
                data = self._get(url, params)
            except Exception as e:
                logger.warning(f"S2 paper search failed for '{query[:60]}...': {e}")
                break

            papers = data.get("data", [])
            if not papers:
                break

            for paper in papers:
                external_ids = paper.get("externalIds") or {}
                doi = external_ids.get("DOI")
                if not doi:
                    continue

                oa_info = paper.get("openAccessPdf") or {}
                all_papers.append({
                    "doi": doi,
                    "title": paper.get("title"),
                    "publication_year": paper.get("year"),
                    "authors": [{"name": a.get("name", "")} for a in (paper.get("authors") or [])],
                    "abstract": paper.get("abstract", ""),
                    "journal": (paper.get("journal") or {}).get("name"),
                    "is_oa": True if oa_info.get("url") else False,
                    "oa_url": oa_info.get("url"),
                    "s2_corpus_id": paper.get("paperId"),
                    "source": "semantic_scholar",
                })

            if len(papers) < 100:
                break
            time.sleep(0.05)

        logger.info(f"S2 paper search '{query[:50]}...' → {len(all_papers)} unique DOIs")
        return all_papers
