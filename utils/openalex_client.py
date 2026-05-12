"""OpenAlex API client for full-text search and source lookup."""

import logging
import time
from typing import Optional

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger("paper_collector")

BASE_URL = "https://api.openalex.org"


class OpenAlexClient:
    def __init__(self, email: str = "your_email@ust.hk", max_retries: int = 5):
        self.email = email
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": f"mailto:{email}"})

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, max=60))
    def _get(self, url: str, params: dict = None) -> dict:
        resp = self.session.get(url, params=params, timeout=30)
        if resp.status_code == 429:
            logger.warning(f"OpenAlex rate limit at {url}")
            raise Exception("429")
        resp.raise_for_status()
        return resp.json()

    def get_journals_by_subfield(self, subfield_ids: list[int] = None) -> list[dict]:
        """
        Discover journals that publish works in the given subfields.
        Uses works group_by to find source IDs, then fetches source details.
        """
        source_ids = set()
        for sid in subfield_ids or [3321]:
            url = f"{BASE_URL}/works"
            params = {
                "filter": f"primary_topic.subfield.id:{sid},publication_year:2024,type:article",
                "group_by": "primary_location.source.id",
                "per_page": 200,
            }
            for page in range(1, 4):
                params["page"] = page
                try:
                    data = self._get(url, params)
                except Exception as e:
                    logger.warning(f"Works group_by failed for subfield {sid}: {e}")
                    break

                groups = data.get("group_by", [])
                if not groups:
                    break

                for g in groups:
                    src_id = g.get("key", "").replace("https://openalex.org/", "")
                    if src_id:
                        source_ids.add(src_id)

                logger.info(f"Subfield {sid} page {page}: {len(groups)} sources")
                time.sleep(0.3)

        logger.info(f"Found {len(source_ids)} unique source IDs across subfields")

        # Fetch source details in batches
        journals = []
        source_list = list(source_ids)
        for i in range(0, len(source_list), 50):
            batch = source_list[i : i + 50]
            ids_str = "|".join(batch)
            url = f"{BASE_URL}/sources"
            params = {
                "filter": f"openalex_id:{ids_str}",
                "per_page": 50,
            }
            try:
                data = self._get(url, params)
                for src in data.get("results", []):
                    journals.append({
                        "name": src.get("display_name"),
                        "issn_l": src.get("issn_l"),
                        "issn_print": next(
                            (n for n in (src.get("issn") or []) if "print" in str(n).lower()),
                            src.get("issn_l"),
                        ),
                        "issn_electronic": next(
                            (n for n in (src.get("issn") or []) if "electronic" in str(n).lower()),
                            None,
                        ),
                        "openalex_source_id": src.get("id", "").replace("https://openalex.org/", ""),
                        "works_count": src.get("works_count", 0),
                        "cited_by_count": src.get("cited_by_count", 0),
                    })
            except Exception as e:
                logger.warning(f"Source batch lookup failed: {e}")
            time.sleep(0.3)

        # Deduplicate by ISSN-L
        seen = set()
        unique = []
        for j in journals:
            key = j["issn_l"]
            if key and key not in seen:
                seen.add(key)
                unique.append(j)

        # Sort by works_count descending
        unique.sort(key=lambda x: x.get("works_count", 0), reverse=True)

        logger.info(f"Fetched {len(unique)} unique journals")
        return unique

    def search_works(
        self,
        query: str,
        source_ids: list[str] = None,
        start_year: int = 2024,
    ) -> list[dict]:
        """
        Search works by query, optionally filtered by journal source IDs.
        OpenAlex searches title + abstract + fulltext n-grams.
        Chunks source_ids into batches of 50 (OpenAlex OR filter limit).
        """
        all_works = []
        seen_dois = set()

        id_batches = []
        if source_ids:
            for i in range(0, len(source_ids), 50):
                id_batches.append(source_ids[i : i + 50])
        else:
            id_batches.append(None)

        for batch in id_batches:
            filter_parts = ["publication_year:>2023", "type:article"]

            if batch:
                ids_str = "|".join(batch)
                filter_parts.append(f"primary_location.source.id:{ids_str}")

            url = f"{BASE_URL}/works"
            params = {
                "search": query,
                "filter": ",".join(filter_parts),
                "per_page": 200,
                "sort": "publication_date:desc",
            }

            for page in range(1, 6):  # Safety cap
                params["page"] = page
                try:
                    data = self._get(url, params)
                except Exception as e:
                    logger.warning(f"OpenAlex search failed for query '{query[:60]}...': {e}")
                    break

                results = data.get("results", [])
                if not results:
                    break

                for work in results:
                    doi = work.get("doi", "")
                    doi = doi.replace("https://doi.org/", "") if doi else None
                    if not doi:
                        continue
                    if doi.lower() in seen_dois:
                        continue
                    seen_dois.add(doi.lower())

                    primary_location = work.get("primary_location") or {}
                    source = primary_location.get("source") or {}

                    all_works.append({
                        "doi": doi,
                        "title": work.get("title"),
                        "publication_year": work.get("publication_year"),
                        "authors": [
                            {"name": a.get("author", {}).get("display_name", ""), "id": a.get("author", {}).get("id", "")}
                            for a in (work.get("authorships") or [])
                        ],
                        "abstract": _extract_abstract(work),
                        "journal": source.get("display_name"),
                        "journal_issn_l": source.get("issn_l"),
                        "openalex_work_id": work.get("id", "").replace("https://openalex.org/", ""),
                        "is_oa": work.get("open_access", {}).get("is_oa", False),
                        "oa_url": work.get("open_access", {}).get("oa_url"),
                        "cited_by_count": work.get("cited_by_count", 0),
                        "source": "openalex",
                    })

                logger.info(f"OpenAlex search '{query[:50]}...' batch {id_batches.index(batch)+1}/{len(id_batches)} page {page}: {len(results)} works")

            logger.info(f"OpenAlex batch complete → cumulative {len(all_works)} DOIs")

        logger.info(f"OpenAlex query '{query[:60]}...' → {len(all_works)} unique DOIs (across {len(id_batches)} source-ID batches)")
        return all_works


    def get_work_by_doi(self, doi: str) -> dict | None:
        """Look up a single work by DOI. Returns enriched metadata or None."""
        clean_doi = doi.replace("https://doi.org/", "").strip().lower()
        url = f"{BASE_URL}/works"
        params = {"filter": f"doi:{clean_doi}", "per_page": 1}
        try:
            data = self._get(url, params)
            results = data.get("results", [])
            if results:
                work = results[0]
                primary_location = work.get("primary_location") or {}
                source = primary_location.get("source") or {}
                return {
                    "doi": clean_doi,
                    "title": work.get("title"),
                    "publication_year": work.get("publication_year"),
                    "journal": source.get("display_name"),
                    "journal_issn_l": source.get("issn_l"),
                    "abstract": _extract_abstract(work),
                    "is_oa": work.get("open_access", {}).get("is_oa", False),
                    "oa_url": work.get("open_access", {}).get("oa_url"),
                    "openalex_work_id": work.get("id", "").replace("https://openalex.org/", ""),
                }
        except Exception as e:
            logger.debug(f"OA DOI lookup failed for {clean_doi}: {e}")
        return None


def _extract_abstract(work: dict) -> str:
    """Extract abstract from OpenAlex work, preferring inverted index."""
    ai = work.get("abstract_inverted_index")
    if ai and isinstance(ai, dict):
        try:
            word_positions = [(word, pos[0]) for word, positions in ai.items() for pos in positions]
            word_positions.sort(key=lambda x: x[1])
            return " ".join(wp[0] for wp in word_positions)
        except Exception:
            pass
    return work.get("abstract", "")
