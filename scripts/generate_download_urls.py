#!/usr/bin/env python3
"""
Generate download URLs for manual browser download.

Creates a list of EZProxy-prefixed URLs that can be opened in a browser
(with active HKUST SSO session) or fed to Zotero.

Output: data/search_results/manual_download_urls.txt
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.config_loader import load_config


def main():
    config = load_config()
    ezproxy_base = config.get("ezproxy", {}).get("base_url", "https://lib.ezproxy.hkust.edu.hk/login?url=")

    candidates_path = Path(__file__).parent.parent / "data" / "search_results" / "deduplicated_candidates.jsonl"
    if not candidates_path.exists():
        print("No candidates found. Run 02_search_papers.py first.")
        sys.exit(1)

    candidates = []
    with open(candidates_path) as f:
        for line in f:
            if line.strip():
                candidates.append(json.loads(line.strip()))

    print(f"Generating download links for {len(candidates)} papers...\n")

    # Generate browser-openable URLs
    urls = []
    for p in candidates:
        doi = p["doi"]
        proxy_url = f"{ezproxy_base}https://doi.org/{doi}"
        urls.append({
            "doi": doi,
            "title": p.get("title", ""),
            "journal": p.get("journal", ""),
            "year": p.get("publication_year", ""),
            "is_oa": p.get("is_oa", False),
            "proxy_url": proxy_url,
            "oa_url": p.get("oa_url", ""),
        })

    # Save JSON for scripting
    json_path = Path(__file__).parent.parent / "data" / "search_results" / "download_urls.json"
    with open(json_path, "w") as f:
        json.dump(urls, f, indent=2, ensure_ascii=False)

    # Save plain text URL list (one per line, for batch opening)
    txt_path = Path(__file__).parent.parent / "data" / "search_results" / "manual_download_urls.txt"
    with open(txt_path, "w") as f:
        for u in urls:
            f.write(f"{u['proxy_url']}\n")

    # Print summary with top papers
    oa_count = sum(1 for u in urls if u["is_oa"])
    print(f"OA papers:      {oa_count}")
    print(f"Paywalled:      {len(urls) - oa_count}")
    print(f"\nJSON metadata:  {json_path}")
    print(f"URL list (txt): {txt_path}")
    print(f"\nSample URLs:")
    for u in urls[:5]:
        print(f"  [{u['year']}] {u['title'][:80]}")
        print(f"    Journal: {u['journal']}")
        print(f"    Proxy:   {u['proxy_url'][:100]}...")
        print()


if __name__ == "__main__":
    main()
