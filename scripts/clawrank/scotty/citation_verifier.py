"""Citation verifier: ground LLM-generated citations against real web sources via SearXNG.

Runs after stage 10 (data_collect) and stage 11 (evidence_build) to verify
that cited sources actually exist. Replaces fabricated citations with real ones
or drops them entirely.
"""
import json
import re
import logging
from typing import Any
from urllib.parse import quote_plus

import requests

logger = logging.getLogger(__name__)

SEARXNG_URL = "http://localhost:8888/search"
TIMEOUT = 10


def search_citation(query: str, max_results: int = 5) -> list[dict]:
    """Search SearXNG for a citation claim. Returns list of {title, url, snippet}."""
    try:
        resp = requests.get(
            SEARXNG_URL,
            params={"q": query, "format": "json"},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("content", ""),
            }
            for r in results[:max_results]
        ]
    except Exception as e:
        logger.warning("SearXNG search failed: %s", e)
        return []


def verify_citation(claim: str, source: str) -> dict:
    """Verify a single citation by searching for the claim + source.

    Returns:
        {
            "original_source": str,
            "original_claim": str,
            "verified": bool,
            "real_url": str or "",
            "real_title": str or "",
            "confidence": "high" | "medium" | "low" | "unverified",
        }
    """
    # Build search query from source name + key terms from the claim
    query = f"{source} {claim[:80]}"
    results = search_citation(query)

    if not results:
        return {
            "original_source": source,
            "original_claim": claim,
            "verified": False,
            "real_url": "",
            "real_title": "",
            "confidence": "unverified",
        }

    # Check if any result is from the claimed source domain/name
    source_lower = source.lower()
    best = None
    best_confidence = "low"

    for r in results:
        url = r.get("url", "").lower()
        title = r.get("title", "").lower()

        # High confidence: URL domain matches source name
        if any(part in url for part in _source_to_domains(source)):
            best = r
            best_confidence = "high"
            break

        # Medium confidence: title mentions source
        if source_lower in title:
            best = r
            best_confidence = "medium"

        # Low confidence: first result is topically relevant
        if best is None:
            best = r
            best_confidence = "low"

    if best:
        return {
            "original_source": source,
            "original_claim": claim,
            "verified": best_confidence in ("high", "medium"),
            "real_url": best.get("url", ""),
            "real_title": best.get("title", ""),
            "confidence": best_confidence,
        }

    return {
        "original_source": source,
        "original_claim": claim,
        "verified": False,
        "real_url": "",
        "real_title": "",
        "confidence": "unverified",
    }


def _source_to_domains(source: str) -> list[str]:
    """Map a source name to likely URL domain fragments."""
    mappings = {
        "nature": ["nature.com"],
        "science": ["science.org", "sciencemag.org"],
        "cell": ["cell.com"],
        "lancet": ["thelancet.com"],
        "frontiers": ["frontiersin.org"],
        "pubmed": ["pubmed.ncbi.nlm.nih.gov", "ncbi.nlm.nih.gov"],
        "usda": ["usda.gov", "ars.usda.gov", "nrcs.usda.gov"],
        "texas a&m": ["tamu.edu", "agrilifeextension.tamu.edu"],
        "asm": ["asm.org"],
        "gut microbes": ["tandfonline.com"],
        "pnas": ["pnas.org"],
    }
    source_lower = source.lower()
    for key, domains in mappings.items():
        if key in source_lower:
            return domains
    # Fallback: try to extract domain-like fragments
    return [source_lower.replace(" ", "").replace("&", "")]


def verify_article_citations(article_json: dict) -> dict:
    """Verify all citations in a stage-10 or stage-12 article output.

    Modifies the article in-place:
    - Citations with real URLs get their url field updated
    - Unverified citations get flagged
    - Returns summary stats

    Args:
        article_json: The pipeline stage output containing citations

    Returns:
        {
            "total": int,
            "verified": int,
            "unverified": int,
            "updated": int,
            "details": list[dict],
        }
    """
    citations = article_json.get("citations", [])
    if not citations:
        # Try other locations
        citations = article_json.get("external_data_points", [])

    if not citations:
        return {"total": 0, "verified": 0, "unverified": 0, "updated": 0, "details": []}

    stats = {"total": len(citations), "verified": 0, "unverified": 0, "updated": 0, "details": []}

    for citation in citations:
        claim = citation.get("claim", citation.get("text", ""))
        source = citation.get("source", citation.get("publisher", ""))

        if not claim or not source:
            continue

        # Skip if already has a real URL (not just a journal homepage)
        existing_url = citation.get("url", "")
        if existing_url and "/article" in existing_url or "/doi/" in existing_url:
            stats["verified"] += 1
            stats["details"].append({
                "source": source,
                "status": "already_verified",
                "url": existing_url,
            })
            continue

        result = verify_citation(claim, source)
        stats["details"].append(result)

        if result["verified"]:
            stats["verified"] += 1
            if result["real_url"] and result["real_url"] != existing_url:
                citation["url"] = result["real_url"]
                citation["verified"] = True
                stats["updated"] += 1
                logger.info("Verified: %s → %s", source, result["real_url"])
        else:
            stats["unverified"] += 1
            citation["verified"] = False
            logger.warning("Unverified: %s — '%s'", source, claim[:60])

    return stats


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Verify citations in a ClawRank article")
    parser.add_argument("input", help="Path to stage JSON artifact with citations")
    parser.add_argument("--drop-unverified", action="store_true", help="Remove unverified citations")
    args = parser.parse_args()

    raw = open(args.input).read()
    if raw.startswith("```"):
        raw = re.sub(r"^```\w*\n", "", raw)
        raw = re.sub(r"\n```\s*$", "", raw)
    article = json.loads(raw)

    stats = verify_article_citations(article)
    print(f"Citations: {stats['total']} total, {stats['verified']} verified, {stats['unverified']} unverified, {stats['updated']} URLs updated")

    if args.drop_unverified:
        citations = article.get("citations", article.get("external_data_points", []))
        article["citations"] = [c for c in citations if c.get("verified", True)]
        print(f"Dropped {stats['unverified']} unverified citations")

    out_path = args.input.replace(".json", "-verified.json")
    with open(out_path, "w") as f:
        json.dump(article, f, indent=2, ensure_ascii=False)
    print(f"Written: {out_path}")
