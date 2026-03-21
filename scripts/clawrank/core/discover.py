#!/usr/bin/env python3
"""
ClawRank Live Discovery Module — Scotty's Green Lab

Comprehensive market intelligence gatherer that finds NEW content topics from
live external sources. Runs BEFORE the world state collector to inject fresh
topic signals from the real world.

Sources:
  1. Google PAA (People Also Ask) — via Scrapling
  2. Google Autocomplete — via suggestqueries API
  3. Reddit — via existing audience-research.py infrastructure
  4. YouTube Transcription — via yt-dlp subtitle extraction
  5. TikTok/Instagram — via yt-dlp
  6. Gardening News — via RSS feeds
  7. arXiv Papers — via arXiv API

Usage:
  python3 scripts/clawrank/core/discover.py                     # Full discovery (all sources)
  python3 scripts/clawrank/core/discover.py --source paa        # PAA only
  python3 scripts/clawrank/core/discover.py --source autocomplete
  python3 scripts/clawrank/core/discover.py --source reddit     # Reddit only
  python3 scripts/clawrank/core/discover.py --source youtube    # YouTube transcription only
  python3 scripts/clawrank/core/discover.py --source tiktok     # TikTok/Instagram only
  python3 scripts/clawrank/core/discover.py --source news       # Gardening news only
  python3 scripts/clawrank/core/discover.py --source arxiv      # arXiv papers only
  python3 scripts/clawrank/core/discover.py --quick             # PAA + autocomplete only (fastest)
  python3 scripts/clawrank/core/discover.py --json              # Print to stdout

Integration:
  The world state builder (world_state.py) should check for a recent discovery
  file at data/clawrank/discovery-YYYY-MM-DD.json and merge new_topic_signals
  into its recommendations.

NOTE (nautix → scottysgreenlab port):
  SEED_KEYWORDS, YOUTUBE_SEARCH_QUERIES, TIKTOK_SEARCH_QUERIES,
  FINANCIAL_NEWS_FEEDS, ARXIV_QUERIES, RELEVANCE_KEYWORDS, and REDDIT_USER_AGENT
  below are nautix-specific placeholders. The scotty domain adapter
  (scripts/clawrank/scotty/adapter.py) overrides these at runtime using
  competitor data from src/data/competitors.json and domain config from
  config.scotty.yaml.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths & Constants
# ---------------------------------------------------------------------------

# scripts/clawrank/core/discover.py → parents[3] = project root
PROJECT_ROOT = Path(__file__).resolve().parents[3]
BLOG_DIR = PROJECT_ROOT / "content" / "blog"
OUTPUT_DIR = PROJECT_ROOT / "data" / "clawrank"
CONFIG_PATH = PROJECT_ROOT / "data" / "content-pipeline" / "config.json"
AUDIENCE_RAW_DIR = PROJECT_ROOT / "data" / "content-pipeline" / "audience-raw"

# yt-dlp binary — aliased through python3.10
YT_DLP_CMD = ["/opt/homebrew/bin/python3.10", "-m", "yt_dlp"]

# Reddit user agent
# NOTE: nautix-specific string; scotty adapter overrides via REDDIT_USER_AGENT module attr
REDDIT_USER_AGENT = "NautixClawRankDiscovery/1.0 (market-intelligence)"

# Rate limiting (seconds)
RATE_LIMIT = {
    "google": 2.0,
    "reddit": 0.7,
    "youtube": 3.0,
    "tiktok": 3.0,
    "arxiv": 3.0,
    "rss": 0.0,
}

# Question detection starters
QUESTION_STARTERS = (
    "who", "what", "when", "where", "why", "how", "should",
    "can", "is", "does", "will", "do", "are", "could", "would",
)

# Seed keywords for PAA and autocomplete
# NOTE: nautix-specific placeholders — scotty adapter injects gardening keywords at runtime
SEED_KEYWORDS = [
    "fort wayne sba loans",
    "illinois po financing",
    "revenue based funding",
    "equipment financing",
    "invoice factoring",
    "merchant cash advance",
    "business loans bad credit",
    "small ticket equipment financing",
]

# YouTube search queries
# NOTE: nautix-specific placeholders — scotty adapter injects gardening queries at runtime
YOUTUBE_SEARCH_QUERIES = [
    "small business loans 2026",
    "SBA loan requirements",
    "equipment financing for small business",
    "merchant cash advance explained",
    "business funding bad credit",
]

# TikTok search queries
# NOTE: nautix-specific placeholders — scotty adapter injects gardening queries at runtime
TIKTOK_SEARCH_QUERIES = [
    "business loans",
    "small business funding",
    "SBA loan",
]

# Financial news RSS feeds
# NOTE: nautix-specific feeds — scotty adapter injects gardening/horticulture RSS feeds at runtime
FINANCIAL_NEWS_FEEDS = [
    ("SBA.gov", "https://www.sba.gov/rss/feed"),
    ("Federal Reserve", "https://www.federalreserve.gov/feeds/press_all.xml"),
    ("NerdWallet", "https://feeds.feedburner.com/NerdWallet"),
    ("American Banker", "https://www.americanbanker.com/feed"),
    ("PYMNTS", "https://www.pymnts.com/feed/"),
]

# arXiv search queries (use AND/OR operators for better precision)
# NOTE: nautix-specific queries — scotty adapter injects gardening/soil science queries at runtime
ARXIV_QUERIES = [
    "ti:lending AND abs:small+business",
    "ti:fintech AND abs:lending",
    "ti:credit AND abs:small+business",
    "abs:merchant+cash+advance",
    "abs:alternative+lending AND abs:fintech",
]

# Business lending relevance keywords (for filtering news/arxiv)
# NOTE: nautix-specific keywords — scotty adapter injects gardening relevance keywords at runtime
RELEVANCE_KEYWORDS = {
    "loan", "lending", "funding", "finance", "fintech", "sba",
    "credit", "business", "small business", "equipment", "invoice",
    "factoring", "capital", "merchant", "cash advance", "revenue",
    "alternative lending", "commercial", "underwriting", "debt",
    "interest rate", "borrower", "lender", "collateral",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_config() -> dict:
    """Load the content pipeline config."""
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return {}


def get_blog_slugs() -> set[str]:
    """Return a set of all existing blog post slugs."""
    slugs = set()
    if BLOG_DIR.exists():
        for f in BLOG_DIR.glob("*.mdx"):
            slugs.add(f.stem)
    return slugs


def get_blog_titles() -> list[str]:
    """Extract titles from blog frontmatter for topic matching."""
    titles = []
    if BLOG_DIR.exists():
        for f in BLOG_DIR.glob("*.mdx"):
            text = f.read_text(encoding="utf-8", errors="ignore")
            match = re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', text, re.MULTILINE)
            if match:
                titles.append(match.group(1).strip())
    return titles


def is_question(text: str) -> bool:
    """Return True if text looks like a question."""
    if not text:
        return False
    stripped = text.strip()
    if "?" in stripped:
        return True
    first_word = re.split(r"\s+", stripped.lower())[0].rstrip(".,;:")
    return first_word in QUESTION_STARTERS


def normalize_topic(text: str) -> str:
    """Normalize a topic string for deduplication and comparison."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def topic_matches_existing(topic: str, slugs: set[str], titles: list[str]) -> bool:
    """Check if a discovered topic is already covered by existing content."""
    norm = normalize_topic(topic)
    norm_words = set(norm.split())

    # Check against slugs (word overlap)
    for slug in slugs:
        slug_words = set(slug.replace("-", " ").split())
        overlap = norm_words & slug_words
        if len(overlap) >= 3 or (len(overlap) >= 2 and len(norm_words) <= 4):
            return True

    # Check against titles (substring or high word overlap)
    for title in titles:
        title_norm = normalize_topic(title)
        title_words = set(title_norm.split())
        overlap = norm_words & title_words
        if len(overlap) >= 3:
            return True
        if norm in title_norm or title_norm in norm:
            return True

    return False


def http_get_raw(url: str, headers: dict | None = None, timeout: int = 20) -> bytes | None:
    """Simple GET request, returns raw bytes or None on error."""
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code}: {url[:80]}...", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  Error: {url[:80]} -> {e}", file=sys.stderr)
        return None


def http_get_json(url: str, headers: dict | None = None, timeout: int = 20) -> dict | list | None:
    """Simple GET request, returns parsed JSON or None."""
    data = http_get_raw(url, headers, timeout)
    if data is None:
        return None
    try:
        return json.loads(data)
    except json.JSONDecodeError:
        return None


def relevance_score(text: str) -> float:
    """Score how relevant a text is to the domain (0.0 to 1.0)."""
    text_lower = text.lower()
    matched = sum(1 for kw in RELEVANCE_KEYWORDS if kw in text_lower)
    return min(1.0, matched / 3.0)


# ---------------------------------------------------------------------------
# Source 1: Google PAA (People Also Ask)
# ---------------------------------------------------------------------------

def collect_paa(seed_keywords: list[str]) -> dict:
    """Scrape Google PAA questions for seed keywords using Scrapling."""
    print("\n  [paa] Collecting People Also Ask questions...", file=sys.stderr)
    result = {
        "queries_searched": 0,
        "questions_found": 0,
        "questions": [],
        "errors": [],
    }

    try:
        from scrapling import Fetcher
    except ImportError:
        result["errors"].append("scrapling not installed — run: pip install scrapling")
        print("  [paa] ERROR: scrapling not installed", file=sys.stderr)
        return result

    fetcher = Fetcher()

    for keyword in seed_keywords:
        result["queries_searched"] += 1
        print(f"  [paa] Searching: {keyword}", file=sys.stderr)

        try:
            encoded = urllib.parse.quote_plus(keyword)
            url = f"https://www.google.com/search?q={encoded}&hl=en&gl=us"
            resp = fetcher.get(url)

            # PAA questions appear in various selectors depending on Google's layout
            paa_questions = []

            # Strategy 1: data-sgrd attribute containers (common PAA wrapper)
            for el in resp.css("div[data-sgrd] span"):
                text = el.text.strip() if el.text else ""
                if text and is_question(text) and len(text) > 15:
                    paa_questions.append(text)

            # Strategy 2: jsname="Cpkphb" (PAA accordion items)
            for el in resp.css('[jsname="Cpkphb"] span'):
                text = el.text.strip() if el.text else ""
                if text and is_question(text) and len(text) > 15:
                    paa_questions.append(text)

            # Strategy 3: aria-expanded divs (accordion pattern)
            for el in resp.css('div[data-lk] span, div[jscontroller] div[role="heading"] span'):
                text = el.text.strip() if el.text else ""
                if text and is_question(text) and len(text) > 15:
                    paa_questions.append(text)

            # Strategy 4: related questions div
            for el in resp.css('div.related-question-pair span'):
                text = el.text.strip() if el.text else ""
                if text and is_question(text) and len(text) > 15:
                    paa_questions.append(text)

            # Strategy 5: broad catch — any span with a question mark in
            # areas that look like PAA
            for el in resp.css('div[data-initq] span, div[data-q] span'):
                text = el.text.strip() if el.text else ""
                if text and "?" in text and len(text) > 15:
                    paa_questions.append(text)

            # Deduplicate
            seen = set()
            unique_questions = []
            for q in paa_questions:
                q_norm = q.lower().strip()
                if q_norm not in seen:
                    seen.add(q_norm)
                    unique_questions.append(q)

            for question in unique_questions:
                result["questions"].append({
                    "query": keyword,
                    "question": question,
                    "source": "google_paa",
                })
                result["questions_found"] += 1

            print(f"    Found {len(unique_questions)} PAA questions", file=sys.stderr)

        except Exception as e:
            error_msg = f"PAA scrape failed for '{keyword}': {e}"
            result["errors"].append(error_msg)
            print(f"    ERROR: {e}", file=sys.stderr)

        time.sleep(RATE_LIMIT["google"])

    print(f"  [paa] Total: {result['questions_found']} questions from "
          f"{result['queries_searched']} queries", file=sys.stderr)
    return result


# ---------------------------------------------------------------------------
# Source 2: Google Autocomplete
# ---------------------------------------------------------------------------

def collect_autocomplete(seed_keywords: list[str]) -> dict:
    """Fetch Google autocomplete suggestions for seed keywords + alphabet modifiers."""
    print("\n  [autocomplete] Collecting suggestions...", file=sys.stderr)
    result = {
        "queries_searched": 0,
        "suggestions_found": 0,
        "top_suggestions": [],
        "errors": [],
    }

    alphabet = list("abcdefghijklmnopqrstuvwxyz")
    all_suggestions: list[dict] = []
    seen_suggestions: set[str] = set()

    for keyword in seed_keywords:
        # Base query (no modifier)
        queries = [keyword] + [f"{keyword} {letter}" for letter in alphabet]

        for query in queries:
            result["queries_searched"] += 1
            encoded = urllib.parse.quote_plus(query)
            url = f"https://suggestqueries.google.com/complete/search?client=firefox&q={encoded}"

            try:
                data = http_get_json(url)
                if data and isinstance(data, list) and len(data) > 1:
                    suggestions = data[1]
                    for suggestion in suggestions:
                        if isinstance(suggestion, str):
                            s_norm = suggestion.lower().strip()
                            if s_norm not in seen_suggestions and s_norm != query.lower():
                                seen_suggestions.add(s_norm)
                                all_suggestions.append({
                                    "seed": keyword,
                                    "modifier": query[len(keyword):].strip() or None,
                                    "suggestion": suggestion,
                                    "source": "google_autocomplete",
                                })
                                result["suggestions_found"] += 1
            except Exception as e:
                result["errors"].append(f"Autocomplete failed for '{query}': {e}")

            time.sleep(RATE_LIMIT["google"])

        print(f"  [autocomplete] {keyword}: "
              f"{sum(1 for s in all_suggestions if s['seed'] == keyword)} unique suggestions",
              file=sys.stderr)

    # Sort by relevance (domain keywords present)
    all_suggestions.sort(
        key=lambda s: relevance_score(s["suggestion"]),
        reverse=True,
    )
    result["top_suggestions"] = all_suggestions[:200]

    print(f"  [autocomplete] Total: {result['suggestions_found']} unique suggestions "
          f"from {result['queries_searched']} queries", file=sys.stderr)
    return result


# ---------------------------------------------------------------------------
# Source 3: Reddit Mining
# ---------------------------------------------------------------------------

def collect_reddit(config: dict) -> dict:
    """Mine Reddit for domain themes and questions."""
    print("\n  [reddit] Mining Reddit for themes...", file=sys.stderr)
    result = {
        "posts_analyzed": 0,
        "themes": [],
        "questions": [],
        "errors": [],
    }

    ar = config.get("audience_research", {})
    subreddits = ar.get("reddit_subreddits", ["smallbusiness", "Entrepreneur", "startups",
                                               "personalfinance", "Banking"])
    search_terms = ar.get("reddit_search_terms", ["business loan", "SBA loan", "funding",
                                                   "line of credit", "equipment financing",
                                                   "working capital"])
    rate_limit = ar.get("reddit_rate_limit_delay", RATE_LIMIT["reddit"])
    min_upvotes = ar.get("min_upvotes_reddit", 2)

    all_posts: list[dict] = []
    seen_ids: set[str] = set()
    cutoff_utc = (datetime.now(timezone.utc) - timedelta(days=7)).timestamp()

    for subreddit in subreddits:
        for term in search_terms:
            encoded_term = urllib.parse.quote(term)
            url = (
                f"https://www.reddit.com/r/{subreddit}/search.json"
                f"?q={encoded_term}&restrict_sr=1&sort=relevance&limit=25&t=week"
            )

            try:
                time.sleep(rate_limit)
                resp = http_get_json(url, headers={"User-Agent": REDDIT_USER_AGENT})
                if not resp:
                    continue

                children = resp.get("data", {}).get("children", [])
                for child in children:
                    data = child.get("data", {})
                    post_id = data.get("id", "")
                    created = data.get("created_utc", 0)
                    score = data.get("score", 0)

                    if (not post_id or post_id in seen_ids
                            or created < cutoff_utc or score < min_upvotes):
                        continue

                    seen_ids.add(post_id)
                    title = data.get("title", "")
                    selftext = data.get("selftext", "")[:500]

                    all_posts.append({
                        "post_id": post_id,
                        "subreddit": subreddit,
                        "title": title,
                        "selftext": selftext,
                        "score": score,
                        "num_comments": data.get("num_comments", 0),
                        "url": f"https://www.reddit.com{data.get('permalink', '')}",
                        "created_utc": int(created),
                        "search_term": term,
                    })

            except Exception as e:
                result["errors"].append(f"Reddit r/{subreddit} '{term}': {e}")

        print(f"  [reddit] r/{subreddit}: {sum(1 for p in all_posts if p['subreddit'] == subreddit)} posts",
              file=sys.stderr)

    result["posts_analyzed"] = len(all_posts)

    # Extract themes via keyword frequency analysis
    word_freq: Counter = Counter()
    bigram_freq: Counter = Counter()
    questions_found: list[dict] = []

    for post in all_posts:
        text = f"{post['title']} {post['selftext']}".lower()
        words = re.findall(r"\b[a-z]{3,}\b", text)
        # Skip common stopwords
        stopwords = {"the", "and", "for", "that", "this", "with", "you", "are",
                     "have", "was", "can", "not", "but", "from", "they", "been",
                     "has", "had", "will", "would", "could", "should", "about",
                     "just", "get", "got", "like", "know", "any", "our", "their",
                     "your", "what", "how", "all", "one", "out", "more", "also",
                     "been", "its", "there", "when", "which", "into", "some",
                     "than", "then", "them", "very", "much", "too", "here",
                     "does", "did"}
        filtered = [w for w in words if w not in stopwords]
        word_freq.update(filtered)

        # Bigrams
        for i in range(len(filtered) - 1):
            bigram = f"{filtered[i]} {filtered[i+1]}"
            bigram_freq.update([bigram])

        # Extract questions
        for sentence in re.split(r"[.!?\n]", f"{post['title']} {post['selftext']}"):
            sentence = sentence.strip()
            if is_question(sentence) and len(sentence) > 20:
                questions_found.append({
                    "question": sentence[:200],
                    "subreddit": post["subreddit"],
                    "score": post["score"],
                    "source": "reddit",
                })

    # Build themes from top bigrams
    themes: list[dict] = []
    for bigram, count in bigram_freq.most_common(30):
        # Only include bigrams relevant to the domain
        if relevance_score(bigram) > 0.0 and count >= 2:
            # Find the post with highest upvotes mentioning this bigram
            top_score = 0
            top_sub = ""
            for post in all_posts:
                if bigram in f"{post['title']} {post['selftext']}".lower():
                    if post["score"] > top_score:
                        top_score = post["score"]
                        top_sub = post["subreddit"]
            themes.append({
                "theme": bigram,
                "mentions": count,
                "upvotes": top_score,
                "source": f"r/{top_sub}" if top_sub else "reddit",
            })

    # Deduplicate questions
    seen_q: set[str] = set()
    unique_questions: list[dict] = []
    for q in sorted(questions_found, key=lambda x: x["score"], reverse=True):
        q_norm = normalize_topic(q["question"])
        if q_norm not in seen_q:
            seen_q.add(q_norm)
            unique_questions.append(q)

    result["themes"] = themes[:20]
    result["questions"] = unique_questions[:30]

    print(f"  [reddit] Total: {result['posts_analyzed']} posts, "
          f"{len(themes)} themes, {len(unique_questions)} questions", file=sys.stderr)
    return result


# ---------------------------------------------------------------------------
# Source 4: YouTube Transcription (via yt-dlp)
# ---------------------------------------------------------------------------

def collect_youtube(search_queries: list[str]) -> dict:
    """Search YouTube and extract transcripts for topic mining."""
    print("\n  [youtube] Searching and transcribing videos...", file=sys.stderr)
    result = {
        "videos_transcribed": 0,
        "topics_extracted": [],
        "errors": [],
    }

    max_per_query = 5
    max_total = 25
    total_processed = 0

    for query in search_queries:
        if total_processed >= max_total:
            break

        print(f"  [youtube] Searching: {query}", file=sys.stderr)

        # Step 1: Search for videos
        try:
            search_cmd = YT_DLP_CMD + [
                "--flat-playlist",
                "--print", "%(id)s\t%(title)s\t%(channel)s\t%(duration)s",
                "--no-warnings",
                f"ytsearch{max_per_query}:{query}",
            ]
            search_result = subprocess.run(
                search_cmd, capture_output=True, text=True, timeout=30,
            )

            if search_result.returncode != 0:
                result["errors"].append(f"yt-dlp search failed for '{query}': {search_result.stderr[:200]}")
                continue

            videos = []
            for line in search_result.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                parts = line.split("\t")
                if len(parts) >= 2:
                    vid_id = parts[0].strip()
                    title = parts[1].strip() if len(parts) > 1 else ""
                    channel = parts[2].strip() if len(parts) > 2 else ""
                    duration = parts[3].strip() if len(parts) > 3 else ""
                    if vid_id and len(vid_id) == 11:
                        videos.append({
                            "id": vid_id,
                            "title": title,
                            "channel": channel,
                            "duration": duration,
                        })

        except subprocess.TimeoutExpired:
            result["errors"].append(f"yt-dlp search timed out for '{query}'")
            continue
        except Exception as e:
            result["errors"].append(f"yt-dlp search error for '{query}': {e}")
            continue

        # Step 2: Download subtitles for each video
        for video in videos[:max_per_query]:
            if total_processed >= max_total:
                break

            vid_id = video["id"]
            vid_url = f"https://www.youtube.com/watch?v={vid_id}"
            print(f"    Transcribing: {video['title'][:60]}...", file=sys.stderr)

            transcript_text = ""
            with tempfile.TemporaryDirectory() as tmpdir:
                try:
                    sub_cmd = YT_DLP_CMD + [
                        "--write-auto-sub",
                        "--sub-lang", "en",
                        "--skip-download",
                        "--sub-format", "vtt",
                        "--output", os.path.join(tmpdir, "%(id)s"),
                        "--no-warnings",
                        vid_url,
                    ]
                    sub_result = subprocess.run(
                        sub_cmd, capture_output=True, text=True, timeout=45,
                    )

                    # Find the subtitle file
                    sub_files = list(Path(tmpdir).glob("*.vtt"))
                    if not sub_files:
                        sub_files = list(Path(tmpdir).glob("*.en.vtt"))
                    if not sub_files:
                        sub_files = list(Path(tmpdir).glob("*"))

                    if sub_files:
                        raw = sub_files[0].read_text(encoding="utf-8", errors="ignore")
                        # Parse VTT: strip timestamps and metadata, keep text
                        lines = []
                        for line in raw.split("\n"):
                            line = line.strip()
                            # Skip VTT header, timestamps, and empty lines
                            if (line.startswith("WEBVTT") or
                                    line.startswith("Kind:") or
                                    line.startswith("Language:") or
                                    line.startswith("NOTE") or
                                    re.match(r"^\d{2}:\d{2}", line) or
                                    re.match(r"^[\d\-]+$", line) or
                                    not line):
                                continue
                            # Strip VTT formatting tags
                            line = re.sub(r"<[^>]+>", "", line)
                            if line:
                                lines.append(line)

                        # Deduplicate consecutive lines (VTT often repeats)
                        deduped = []
                        for line in lines:
                            if not deduped or line != deduped[-1]:
                                deduped.append(line)

                        transcript_text = " ".join(deduped)

                except subprocess.TimeoutExpired:
                    result["errors"].append(f"Subtitle download timed out for {vid_id}")
                    continue
                except Exception as e:
                    result["errors"].append(f"Subtitle error for {vid_id}: {e}")
                    continue

            # Step 3: Extract topics and questions from transcript
            key_topics = []
            questions_asked = []

            if transcript_text:
                # Extract questions
                sentences = re.split(r"[.!?]+", transcript_text)
                for sentence in sentences:
                    sentence = sentence.strip()
                    if is_question(sentence) and 15 < len(sentence) < 200:
                        questions_asked.append(sentence)

                # Extract key topics via bigram frequency
                words = re.findall(r"\b[a-z]{3,}\b", transcript_text.lower())
                stopwords = {"the", "and", "for", "that", "this", "with", "you",
                             "are", "have", "was", "can", "not", "but", "from",
                             "they", "been", "has", "had", "will", "would",
                             "could", "should", "about", "just", "get", "got",
                             "like", "know", "any", "going", "right", "really",
                             "actually", "want", "thing", "think", "okay",
                             "yeah", "gonna", "gotta", "need", "said", "look",
                             "make", "take", "come", "back"}
                filtered = [w for w in words if w not in stopwords]
                bigram_counter: Counter = Counter()
                for i in range(len(filtered) - 1):
                    bg = f"{filtered[i]} {filtered[i+1]}"
                    bigram_counter.update([bg])

                for bg, count in bigram_counter.most_common(10):
                    if relevance_score(bg) > 0.0 and count >= 3:
                        key_topics.append(bg)

            result["topics_extracted"].append({
                "video_id": vid_id,
                "title": video["title"],
                "channel": video["channel"],
                "search_query": query,
                "url": vid_url,
                "has_transcript": bool(transcript_text),
                "transcript_length": len(transcript_text),
                "key_topics": key_topics[:10],
                "questions_asked": questions_asked[:10],
            })
            result["videos_transcribed"] += 1
            total_processed += 1

            time.sleep(RATE_LIMIT["youtube"])

    print(f"  [youtube] Total: {result['videos_transcribed']} videos transcribed",
          file=sys.stderr)
    return result


# ---------------------------------------------------------------------------
# Source 5: TikTok/Instagram (via yt-dlp)
# ---------------------------------------------------------------------------

def collect_tiktok(search_queries: list[str]) -> dict:
    """Search TikTok for domain content and extract captions."""
    print("\n  [tiktok] Searching TikTok/Instagram...", file=sys.stderr)
    result = {
        "posts_analyzed": 0,
        "trending_topics": [],
        "errors": [],
    }

    max_per_platform = 10
    all_captions: list[dict] = []

    for query in search_queries:
        encoded = urllib.parse.quote_plus(query)
        print(f"  [tiktok] Searching: {query}", file=sys.stderr)

        # TikTok search via yt-dlp
        try:
            tiktok_url = f"https://www.tiktok.com/search?q={encoded}"
            search_cmd = YT_DLP_CMD + [
                "--flat-playlist",
                "--print", "%(id)s\t%(title)s\t%(uploader)s\t%(like_count)s",
                "--playlist-items", f"1:{max_per_platform}",
                "--no-warnings",
                tiktok_url,
            ]
            search_result = subprocess.run(
                search_cmd, capture_output=True, text=True, timeout=45,
            )

            if search_result.returncode == 0 and search_result.stdout.strip():
                for line in search_result.stdout.strip().split("\n"):
                    if not line.strip():
                        continue
                    parts = line.split("\t")
                    vid_id = parts[0].strip() if len(parts) > 0 else ""
                    title = parts[1].strip() if len(parts) > 1 else ""
                    uploader = parts[2].strip() if len(parts) > 2 else ""
                    likes = parts[3].strip() if len(parts) > 3 else "0"

                    if vid_id and title:
                        all_captions.append({
                            "platform": "tiktok",
                            "id": vid_id,
                            "caption": title,
                            "uploader": uploader,
                            "likes": int(likes) if likes.isdigit() else 0,
                            "search_query": query,
                        })

            else:
                if search_result.stderr:
                    result["errors"].append(
                        f"TikTok search '{query}': {search_result.stderr[:200]}")

        except subprocess.TimeoutExpired:
            result["errors"].append(f"TikTok search timed out for '{query}'")
        except Exception as e:
            result["errors"].append(f"TikTok search error for '{query}': {e}")

        time.sleep(RATE_LIMIT["tiktok"])

    result["posts_analyzed"] = len(all_captions)

    # Extract trending topics from captions
    if all_captions:
        word_freq: Counter = Counter()
        bigram_freq: Counter = Counter()
        for post in all_captions:
            text = post["caption"].lower()
            words = re.findall(r"\b[a-z]{3,}\b", text)
            stopwords = {"the", "and", "for", "that", "this", "with", "you",
                         "are", "have", "was", "not", "how", "can"}
            filtered = [w for w in words if w not in stopwords]
            word_freq.update(filtered)
            for i in range(len(filtered) - 1):
                bg = f"{filtered[i]} {filtered[i+1]}"
                bigram_freq.update([bg])

        for bg, count in bigram_freq.most_common(15):
            if relevance_score(bg) > 0.0 and count >= 2:
                result["trending_topics"].append({
                    "topic": bg,
                    "mentions": count,
                    "platform": "tiktok",
                    "source": "tiktok",
                })

    # Include top posts by likes
    top_posts = sorted(all_captions, key=lambda x: x["likes"], reverse=True)[:10]
    result["top_posts"] = [
        {
            "platform": p["platform"],
            "caption": p["caption"][:200],
            "uploader": p["uploader"],
            "likes": p["likes"],
            "search_query": p["search_query"],
        }
        for p in top_posts
    ]

    print(f"  [tiktok] Total: {result['posts_analyzed']} posts, "
          f"{len(result['trending_topics'])} trending topics", file=sys.stderr)
    return result


# ---------------------------------------------------------------------------
# Source 6: News (RSS feeds)
# ---------------------------------------------------------------------------

def collect_news() -> dict:
    """Parse news RSS feeds for domain-relevant content."""
    print("\n  [news] Parsing news feeds...", file=sys.stderr)
    result = {
        "articles_found": 0,
        "relevant_articles": [],
        "errors": [],
    }

    cutoff = datetime.now(timezone.utc) - timedelta(days=7)

    for feed_name, feed_url in FINANCIAL_NEWS_FEEDS:
        print(f"  [news] Fetching: {feed_name}...", file=sys.stderr)

        try:
            raw = http_get_raw(feed_url, timeout=15)
            if not raw:
                result["errors"].append(f"Failed to fetch {feed_name}: no response")
                continue

            # Try feedparser first (more robust), fall back to raw XML
            try:
                import feedparser
                feed = feedparser.parse(raw)
                entries = feed.entries
            except ImportError:
                # Fallback to ElementTree
                entries = _parse_rss_xml(raw)

            feed_count = 0
            for entry in entries:
                # Extract fields (feedparser vs raw dict)
                if hasattr(entry, "title"):
                    title = entry.title
                    link = getattr(entry, "link", "")
                    summary = getattr(entry, "summary", getattr(entry, "description", ""))
                    published = getattr(entry, "published", getattr(entry, "updated", ""))
                else:
                    title = entry.get("title", "")
                    link = entry.get("link", "")
                    summary = entry.get("summary", entry.get("description", ""))
                    published = entry.get("published", entry.get("updated", ""))

                if not title:
                    continue

                # Check relevance
                combined_text = f"{title} {summary}"
                score = relevance_score(combined_text)
                if score < 0.3:
                    continue

                # Parse date if possible
                pub_date = _parse_rss_date(published) if published else None
                if pub_date and pub_date < cutoff:
                    continue

                result["articles_found"] += 1
                feed_count += 1

                # Determine article relevance category
                rel_category = _categorize_article(combined_text)

                result["relevant_articles"].append({
                    "title": title[:200],
                    "source": feed_name,
                    "url": link,
                    "date": published[:30] if published else "",
                    "summary": _clean_html(summary)[:300],
                    "relevance": rel_category,
                    "relevance_score": round(score, 2),
                })

            print(f"    {feed_name}: {feed_count} relevant articles", file=sys.stderr)

        except Exception as e:
            error_msg = f"RSS parse error for {feed_name}: {e}"
            result["errors"].append(error_msg)
            print(f"    ERROR: {e}", file=sys.stderr)

    # Sort by relevance score
    result["relevant_articles"].sort(key=lambda x: x["relevance_score"], reverse=True)
    result["relevant_articles"] = result["relevant_articles"][:30]

    print(f"  [news] Total: {result['articles_found']} relevant articles", file=sys.stderr)
    return result


def _parse_rss_xml(raw: bytes) -> list[dict]:
    """Fallback RSS parser using ElementTree."""
    entries = []
    try:
        root = ET.fromstring(raw)
        # Handle both RSS 2.0 and Atom formats
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        # RSS 2.0
        for item in root.findall(".//item"):
            entries.append({
                "title": _el_text(item, "title"),
                "link": _el_text(item, "link"),
                "description": _el_text(item, "description"),
                "published": _el_text(item, "pubDate"),
            })

        # Atom
        for entry in root.findall("atom:entry", ns):
            link_el = entry.find("atom:link", ns)
            entries.append({
                "title": _el_text_ns(entry, "title", ns),
                "link": link_el.get("href", "") if link_el is not None else "",
                "summary": _el_text_ns(entry, "summary", ns),
                "updated": _el_text_ns(entry, "updated", ns),
            })
    except ET.ParseError:
        pass
    return entries


def _el_text(parent: ET.Element, tag: str) -> str:
    """Get text content of a child element."""
    el = parent.find(tag)
    return el.text.strip() if el is not None and el.text else ""


def _el_text_ns(parent: ET.Element, tag: str, ns: dict) -> str:
    """Get text content of a namespaced child element."""
    el = parent.find(f"atom:{tag}", ns)
    return el.text.strip() if el is not None and el.text else ""


def _parse_rss_date(date_str: str) -> datetime | None:
    """Parse common RSS date formats into a timezone-aware datetime."""
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",       # RFC 822
        "%a, %d %b %Y %H:%M:%S %Z",       # RFC 822 with named TZ
        "%Y-%m-%dT%H:%M:%S%z",              # ISO 8601
        "%Y-%m-%dT%H:%M:%SZ",               # ISO 8601 UTC
        "%Y-%m-%d %H:%M:%S",                # Simple datetime
        "%Y-%m-%d",                          # Date only
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, TypeError):
            continue
    return None


def _clean_html(text: str) -> str:
    """Strip HTML tags from text."""
    return re.sub(r"<[^>]+>", "", text).strip()


def _categorize_article(text: str) -> str:
    """Categorize a news article by topic."""
    text_lower = text.lower()
    categories = [
        ("SBA policy change", ["sba", "policy", "rule", "regulation", "program"]),
        ("Interest rate update", ["interest rate", "federal reserve", "fed rate", "rate cut", "rate hike"]),
        ("Fintech innovation", ["fintech", "technology", "ai", "digital", "platform", "startup"]),
        ("Small business lending trend", ["small business", "lending", "loan", "credit"]),
        ("Alternative lending", ["alternative", "online lend", "marketplace", "p2p"]),
        ("Equipment financing", ["equipment", "financing", "leasing"]),
        ("Economic outlook", ["economy", "recession", "gdp", "employment", "inflation"]),
    ]

    best_category = "Business lending"
    best_score = 0
    for category, keywords in categories:
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > best_score:
            best_score = score
            best_category = category

    return best_category


# ---------------------------------------------------------------------------
# Source 7: arXiv Papers
# ---------------------------------------------------------------------------

def collect_arxiv() -> dict:
    """Search arXiv for recent domain-relevant papers."""
    print("\n  [arxiv] Searching arXiv for recent papers...", file=sys.stderr)
    result = {
        "papers_found": 0,
        "relevant_papers": [],
        "errors": [],
    }

    for query in ARXIV_QUERIES:
        print(f"  [arxiv] Searching: {query}", file=sys.stderr)
        # arXiv queries already use field prefixes (ti:, abs:) and operators
        encoded = urllib.parse.quote(query, safe=":")
        url = (
            f"http://export.arxiv.org/api/query"
            f"?search_query={encoded}"
            f"&sortBy=submittedDate&sortOrder=descending&max_results=10"
        )

        try:
            raw = http_get_raw(url, timeout=15)
            if not raw:
                result["errors"].append(f"arXiv query failed: {query}")
                continue

            root = ET.fromstring(raw)
            ns = {"atom": "http://www.w3.org/2005/Atom"}

            entries_found = 0
            for entry in root.findall("atom:entry", ns):
                title = _el_text_ns(entry, "title", ns)
                summary = _el_text_ns(entry, "summary", ns)
                published = _el_text_ns(entry, "published", ns)

                # Get link
                link = ""
                for link_el in entry.findall("atom:link", ns):
                    if link_el.get("type") == "text/html":
                        link = link_el.get("href", "")
                        break
                if not link:
                    id_el = entry.find("atom:id", ns)
                    link = id_el.text.strip() if id_el is not None and id_el.text else ""

                # Get authors
                authors = []
                for author_el in entry.findall("atom:author", ns):
                    name_el = author_el.find("atom:name", ns)
                    if name_el is not None and name_el.text:
                        authors.append(name_el.text.strip())

                if not title:
                    continue

                # Check relevance (lower threshold for arXiv since queries
                # are already targeted and academic language differs)
                combined = f"{title} {summary}"
                score = relevance_score(combined)
                if score < 0.15:
                    continue

                result["papers_found"] += 1
                entries_found += 1

                result["relevant_papers"].append({
                    "title": re.sub(r"\s+", " ", title),
                    "abstract_excerpt": re.sub(r"\s+", " ", summary)[:400],
                    "authors": authors[:3],
                    "date": published[:10] if published else "",
                    "url": link,
                    "search_query": query,
                    "relevance_score": round(score, 2),
                })

            print(f"    Found {entries_found} relevant papers", file=sys.stderr)

        except Exception as e:
            result["errors"].append(f"arXiv error for '{query}': {e}")
            print(f"    ERROR: {e}", file=sys.stderr)

        time.sleep(RATE_LIMIT["arxiv"])

    # Deduplicate by title
    seen_titles: set[str] = set()
    unique_papers: list[dict] = []
    for paper in result["relevant_papers"]:
        t_norm = normalize_topic(paper["title"])
        if t_norm not in seen_titles:
            seen_titles.add(t_norm)
            unique_papers.append(paper)

    result["relevant_papers"] = unique_papers
    result["papers_found"] = len(unique_papers)

    print(f"  [arxiv] Total: {result['papers_found']} unique relevant papers", file=sys.stderr)
    return result


# ---------------------------------------------------------------------------
# Topic Signal Cross-Referencing
# ---------------------------------------------------------------------------

def build_topic_signals(sources: dict, slugs: set[str], titles: list[str]) -> list[dict]:
    """Cross-reference discovered topics against existing blog inventory
    to identify genuinely NEW topics that aren't covered yet."""
    print("\n  [signals] Cross-referencing topics against existing content...", file=sys.stderr)

    # Collect all discovered topics with their sources
    topic_sources: dict[str, list[str]] = defaultdict(list)
    topic_details: dict[str, dict] = {}

    # PAA questions -> topics
    paa_data = sources.get("paa", {})
    for q in paa_data.get("questions", []):
        topic = normalize_topic(q["question"])
        if topic and len(topic) > 10:
            topic_sources[topic].append("google_paa")
            if topic not in topic_details:
                topic_details[topic] = {"raw": q["question"]}

    # Autocomplete suggestions -> topics
    ac_data = sources.get("autocomplete", {})
    for s in ac_data.get("top_suggestions", []):
        topic = normalize_topic(s["suggestion"])
        if topic and len(topic) > 10:
            topic_sources[topic].append("google_autocomplete")
            if topic not in topic_details:
                topic_details[topic] = {"raw": s["suggestion"]}

    # Reddit themes -> topics
    reddit_data = sources.get("reddit", {})
    for theme in reddit_data.get("themes", []):
        topic = normalize_topic(theme["theme"])
        if topic:
            topic_sources[topic].append("reddit")
            if topic not in topic_details:
                topic_details[topic] = {"raw": theme["theme"]}

    for q in reddit_data.get("questions", []):
        topic = normalize_topic(q["question"])
        if topic and len(topic) > 10:
            topic_sources[topic].append("reddit")
            if topic not in topic_details:
                topic_details[topic] = {"raw": q["question"]}

    # YouTube topics -> topics
    yt_data = sources.get("youtube", {})
    for video in yt_data.get("topics_extracted", []):
        for kt in video.get("key_topics", []):
            topic = normalize_topic(kt)
            if topic:
                topic_sources[topic].append("youtube")
                if topic not in topic_details:
                    topic_details[topic] = {"raw": kt}

        for q in video.get("questions_asked", []):
            topic = normalize_topic(q)
            if topic and len(topic) > 10:
                topic_sources[topic].append("youtube")
                if topic not in topic_details:
                    topic_details[topic] = {"raw": q}

    # TikTok topics
    tiktok_data = sources.get("tiktok", {})
    for t in tiktok_data.get("trending_topics", []):
        topic = normalize_topic(t["topic"])
        if topic:
            topic_sources[topic].append("tiktok")
            if topic not in topic_details:
                topic_details[topic] = {"raw": t["topic"]}

    # News article titles -> topics
    news_data = sources.get("news", {})
    for article in news_data.get("relevant_articles", []):
        topic = normalize_topic(article["title"])
        if topic and len(topic) > 10:
            topic_sources[topic].append("news")
            if topic not in topic_details:
                topic_details[topic] = {"raw": article["title"]}

    # arXiv paper titles -> topics
    arxiv_data = sources.get("arxiv", {})
    for paper in arxiv_data.get("relevant_papers", []):
        topic = normalize_topic(paper["title"])
        if topic and len(topic) > 10:
            topic_sources[topic].append("arxiv")
            if topic not in topic_details:
                topic_details[topic] = {"raw": paper["title"]}

    # Merge similar topics (fuzzy dedup by word overlap)
    merged_topics: dict[str, dict] = {}
    for topic, src_list in topic_sources.items():
        # Check if this topic is similar to an already-merged one
        matched = False
        topic_words = set(topic.split())
        for existing_topic in list(merged_topics.keys()):
            existing_words = set(existing_topic.split())
            overlap = topic_words & existing_words
            # If >60% word overlap with an existing topic, merge
            if len(overlap) >= 2 and len(overlap) / min(len(topic_words), len(existing_words)) > 0.6:
                merged_topics[existing_topic]["sources"].extend(src_list)
                merged_topics[existing_topic]["signal_count"] += len(src_list)
                matched = True
                break

        if not matched:
            merged_topics[topic] = {
                "topic": topic_details.get(topic, {}).get("raw", topic),
                "sources": list(src_list),
                "signal_count": len(src_list),
            }

    # Check each topic against existing blog inventory
    signals: list[dict] = []
    for topic_key, data in merged_topics.items():
        existing = topic_matches_existing(topic_key, slugs, titles)

        # Calculate priority:
        # - More sources = higher priority
        # - Questions get a boost
        # - PAA/autocomplete signals get a boost (search demand)
        priority = min(10.0, data["signal_count"] * 2.0)

        # Boost for search-demand signals
        source_set = set(data["sources"])
        if "google_paa" in source_set:
            priority += 1.5
        if "google_autocomplete" in source_set:
            priority += 1.0
        if "reddit" in source_set:
            priority += 0.5
        if "youtube" in source_set:
            priority += 0.5

        # Penalize if already covered
        if existing:
            priority *= 0.3

        priority = round(min(10.0, priority), 1)

        # Deduplicate source list
        unique_sources = list(dict.fromkeys(data["sources"]))

        signals.append({
            "topic": data["topic"],
            "signal_count": data["signal_count"],
            "sources": unique_sources,
            "existing_coverage": existing,
            "priority": priority,
        })

    # Sort by priority descending, then by signal count
    signals.sort(key=lambda x: (x["priority"], x["signal_count"]), reverse=True)

    # Keep top 50
    signals = signals[:50]

    new_count = sum(1 for s in signals if not s["existing_coverage"])
    existing_count = sum(1 for s in signals if s["existing_coverage"])
    print(f"  [signals] {len(signals)} topic signals: "
          f"{new_count} new, {existing_count} already covered", file=sys.stderr)

    return signals


# ---------------------------------------------------------------------------
# Main Orchestrator
# ---------------------------------------------------------------------------

ALL_SOURCES = ["paa", "autocomplete", "reddit", "youtube", "tiktok", "news", "arxiv"]
QUICK_SOURCES = ["paa", "autocomplete"]


def run_discovery(
    sources_to_run: list[str],
    output_json: bool = False,
) -> dict:
    """Run the full discovery pipeline for the requested sources."""
    started = datetime.now(timezone.utc)
    config = load_config()

    print(f"\nClawRank Live Discovery", file=sys.stderr)
    print(f"{'=' * 55}", file=sys.stderr)
    print(f"  Started: {started.isoformat()}", file=sys.stderr)
    print(f"  Sources: {', '.join(sources_to_run)}", file=sys.stderr)
    print(f"{'=' * 55}", file=sys.stderr)

    # Load existing blog inventory for cross-referencing
    slugs = get_blog_slugs()
    titles = get_blog_titles()
    print(f"\n  Existing blog inventory: {len(slugs)} articles", file=sys.stderr)

    collected_sources: dict = {}
    errors_by_source: dict[str, list[str]] = {}

    # --- Source 1: PAA ---
    if "paa" in sources_to_run:
        try:
            paa_result = collect_paa(SEED_KEYWORDS)
            collected_sources["paa"] = paa_result
            if paa_result.get("errors"):
                errors_by_source["paa"] = paa_result["errors"]
        except Exception as e:
            collected_sources["paa"] = {"error": str(e), "questions": []}
            errors_by_source["paa"] = [str(e)]
            print(f"  [paa] FATAL: {e}", file=sys.stderr)

    # --- Source 2: Autocomplete ---
    if "autocomplete" in sources_to_run:
        try:
            ac_result = collect_autocomplete(SEED_KEYWORDS)
            collected_sources["autocomplete"] = ac_result
            if ac_result.get("errors"):
                errors_by_source["autocomplete"] = ac_result["errors"]
        except Exception as e:
            collected_sources["autocomplete"] = {"error": str(e), "top_suggestions": []}
            errors_by_source["autocomplete"] = [str(e)]
            print(f"  [autocomplete] FATAL: {e}", file=sys.stderr)

    # --- Source 3: Reddit ---
    if "reddit" in sources_to_run:
        try:
            reddit_result = collect_reddit(config)
            collected_sources["reddit"] = reddit_result
            if reddit_result.get("errors"):
                errors_by_source["reddit"] = reddit_result["errors"]
        except Exception as e:
            collected_sources["reddit"] = {"error": str(e), "themes": [], "questions": []}
            errors_by_source["reddit"] = [str(e)]
            print(f"  [reddit] FATAL: {e}", file=sys.stderr)

    # --- Source 4: YouTube ---
    if "youtube" in sources_to_run:
        try:
            yt_result = collect_youtube(YOUTUBE_SEARCH_QUERIES)
            collected_sources["youtube"] = yt_result
            if yt_result.get("errors"):
                errors_by_source["youtube"] = yt_result["errors"]
        except Exception as e:
            collected_sources["youtube"] = {"error": str(e), "topics_extracted": []}
            errors_by_source["youtube"] = [str(e)]
            print(f"  [youtube] FATAL: {e}", file=sys.stderr)

    # --- Source 5: TikTok ---
    if "tiktok" in sources_to_run:
        try:
            tiktok_result = collect_tiktok(TIKTOK_SEARCH_QUERIES)
            collected_sources["tiktok"] = tiktok_result
            if tiktok_result.get("errors"):
                errors_by_source["tiktok"] = tiktok_result["errors"]
        except Exception as e:
            collected_sources["tiktok"] = {"error": str(e), "trending_topics": []}
            errors_by_source["tiktok"] = [str(e)]
            print(f"  [tiktok] FATAL: {e}", file=sys.stderr)

    # --- Source 6: News ---
    if "news" in sources_to_run:
        try:
            news_result = collect_news()
            collected_sources["news"] = news_result
            if news_result.get("errors"):
                errors_by_source["news"] = news_result["errors"]
        except Exception as e:
            collected_sources["news"] = {"error": str(e), "relevant_articles": []}
            errors_by_source["news"] = [str(e)]
            print(f"  [news] FATAL: {e}", file=sys.stderr)

    # --- Source 7: arXiv ---
    if "arxiv" in sources_to_run:
        try:
            arxiv_result = collect_arxiv()
            collected_sources["arxiv"] = arxiv_result
            if arxiv_result.get("errors"):
                errors_by_source["arxiv"] = arxiv_result["errors"]
        except Exception as e:
            collected_sources["arxiv"] = {"error": str(e), "relevant_papers": []}
            errors_by_source["arxiv"] = [str(e)]
            print(f"  [arxiv] FATAL: {e}", file=sys.stderr)

    # --- Cross-reference and build topic signals ---
    topic_signals = build_topic_signals(collected_sources, slugs, titles)

    elapsed = (datetime.now(timezone.utc) - started).total_seconds()

    # --- Build output ---
    output = {
        "discovered_at": started.isoformat(),
        "elapsed_seconds": round(elapsed, 1),
        "sources_requested": sources_to_run,
        "sources": collected_sources,
        "new_topic_signals": topic_signals,
        "summary": {
            "total_signals": len(topic_signals),
            "new_topics": sum(1 for s in topic_signals if not s["existing_coverage"]),
            "existing_topics_reinforced": sum(1 for s in topic_signals if s["existing_coverage"]),
            "top_priority_topics": [
                {"topic": s["topic"], "priority": s["priority"], "sources": s["sources"]}
                for s in topic_signals[:10] if not s["existing_coverage"]
            ],
        },
        "errors": errors_by_source if errors_by_source else None,
        "_integration_note": (
            "The world state builder (world_state.py) should check for this file "
            "at data/clawrank/discovery-YYYY-MM-DD.json and merge new_topic_signals "
            "into its write_new recommendations. Topics with existing_coverage=false "
            "and priority>=7 are strong candidates for new content."
        ),
    }

    # Print summary
    print(f"\n{'=' * 55}", file=sys.stderr)
    print(f"  Discovery Complete ({elapsed:.1f}s)", file=sys.stderr)
    print(f"{'=' * 55}", file=sys.stderr)
    print(f"  Sources collected: {len(collected_sources)}/{len(sources_to_run)}", file=sys.stderr)
    print(f"  Topic signals: {len(topic_signals)}", file=sys.stderr)
    new_high = [s for s in topic_signals if not s["existing_coverage"] and s["priority"] >= 7]
    print(f"  New high-priority topics (>=7): {len(new_high)}", file=sys.stderr)

    if new_high:
        print(f"\n  Top new topics:", file=sys.stderr)
        for i, sig in enumerate(new_high[:5], 1):
            print(f"    {i}. [P{sig['priority']}] {sig['topic']}", file=sys.stderr)
            print(f"       Sources: {', '.join(sig['sources'])}", file=sys.stderr)

    if errors_by_source:
        total_errors = sum(len(v) for v in errors_by_source.values())
        print(f"\n  Errors: {total_errors} across {len(errors_by_source)} sources", file=sys.stderr)

    return output


def main():
    parser = argparse.ArgumentParser(
        description="ClawRank Live Discovery — market intelligence gatherer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 scripts/clawrank/core/discover.py                     # Full discovery
  python3 scripts/clawrank/core/discover.py --source paa        # PAA only
  python3 scripts/clawrank/core/discover.py --source reddit     # Reddit only
  python3 scripts/clawrank/core/discover.py --source youtube    # YouTube transcription
  python3 scripts/clawrank/core/discover.py --source tiktok     # TikTok/Instagram
  python3 scripts/clawrank/core/discover.py --source news       # News RSS
  python3 scripts/clawrank/core/discover.py --source arxiv      # arXiv papers
  python3 scripts/clawrank/core/discover.py --quick             # PAA + autocomplete only
  python3 scripts/clawrank/core/discover.py --json              # Print to stdout
        """,
    )
    parser.add_argument(
        "--source",
        choices=ALL_SOURCES,
        help="Run a single source only",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Quick mode: PAA + autocomplete only (fastest)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON to stdout instead of writing to file",
    )
    args = parser.parse_args()

    # Determine which sources to run
    if args.source:
        sources = [args.source]
    elif args.quick:
        sources = QUICK_SOURCES
    else:
        sources = ALL_SOURCES

    # Run discovery
    output = run_discovery(sources, output_json=args.json)

    if args.json:
        print(json.dumps(output, indent=2, default=str))
    else:
        # Write to file
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now().strftime("%Y-%m-%d")
        output_path = OUTPUT_DIR / f"discovery-{date_str}.json"
        output_path.write_text(
            json.dumps(output, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"\n  Written to: {output_path}", file=sys.stderr)

        # Summary to stdout for piping
        summary = output.get("summary", {})
        print(f"\n--- ClawRank Discovery Summary ({date_str}) ---")
        print(f"Total signals:     {summary.get('total_signals', 0)}")
        print(f"New topics:        {summary.get('new_topics', 0)}")
        print(f"Reinforced:        {summary.get('existing_topics_reinforced', 0)}")

        top = summary.get("top_priority_topics", [])
        if top:
            print(f"\nTop new topics:")
            for i, t in enumerate(top[:5], 1):
                print(f"  {i}. [P{t['priority']}] {t['topic']}")
                print(f"     Sources: {', '.join(t['sources'])}")


if __name__ == "__main__":
    main()
