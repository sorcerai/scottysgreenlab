#!/usr/bin/env python3
"""
process-transcripts.py

Reads TikTok transcript JSON files, splits them into 3 document levels,
and upserts them into brain_documents (no embeddings — embed separately).

Format: each file is a double-encoded JSON string containing:
  { "text": "<full transcript>", "sentences": [...] }

Levels:
  1 (transcript_video)    — summary: title + first 2000 chars of text
  2 (transcript_section)  — ~500-word logical chunks of the full text
  3 (transcript_paragraph)— ~150-word segments with sliding-window context
"""

import os
import re
import json
import hashlib
import sys
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values

# ── Config ─────────────────────────────────────────────────────────────────────

TRANSCRIPTS_DIR = "/Users/ariapramesi/repos/scottysfermentedfoods/transcripts/"
DB_URL = (
    "postgresql://tsdbadmin:l9psydr9pgsycfhl"
    "@wiixc9eeb7.yxnlaf6ea7.tsdb.cloud.timescale.com:37178/tsdb"
    "?sslmode=require"
)

BATCH_SIZE = 50          # files per database commit cycle
SECTION_WORDS = 500      # target words per section (level 2)
PARA_WORDS = 150         # target words per paragraph (level 3)
SUMMARY_CHARS = 2000     # chars used for level-1 summary text

# ── Helpers ────────────────────────────────────────────────────────────────────

def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


def parse_filename(fname: str):
    """
    Return (video_id, title) from a filename like:
      "Some title text... [7134054458765413675].json"
    """
    stem = fname[:-5] if fname.endswith(".json") else fname
    # video_id is the last bracketed number
    m = re.search(r"\[(\d+)\]\s*$", stem)
    if not m:
        return None, stem.strip()
    video_id = m.group(1)
    # title = everything before the last [...] block, strip trailing ellipsis / whitespace
    title = stem[: m.start()].rstrip(". \t")
    return video_id, title


def load_transcript(path: str):
    """
    Parse the double-encoded JSON and return the clean transcript text.
    Returns None on any error.
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = fh.read()
        outer = json.loads(raw)
        if isinstance(outer, str):
            inner = json.loads(outer)
        elif isinstance(outer, dict):
            inner = outer
        else:
            return None
        text = inner.get("text", "")
        return text if isinstance(text, str) else None
    except Exception as exc:
        print(f"  [WARN] Failed to parse {path}: {exc}", file=sys.stderr)
        return None


def split_into_sections(text: str, target_words: int = SECTION_WORDS) -> list[str]:
    """
    Split text into chunks of ~target_words words.
    Prefers to break on sentence boundaries ('. ' or '\n').
    """
    if not text.strip():
        return []

    words = text.split()
    if len(words) <= target_words:
        return [text]

    chunks = []
    current_words = []
    current_count = 0

    sentences = re.split(r"(?<=[.!?])\s+", text)
    for sentence in sentences:
        sw = sentence.split()
        if current_count + len(sw) > target_words and current_words:
            chunks.append(" ".join(current_words))
            current_words = sw
            current_count = len(sw)
        else:
            current_words.extend(sw)
            current_count += len(sw)

    if current_words:
        chunks.append(" ".join(current_words))

    return [c for c in chunks if c.strip()]


def split_into_paragraphs(text: str, target_words: int = PARA_WORDS) -> list[str]:
    """
    Split text into ~target_words word segments.
    Try double-newline paragraph breaks first; fall back to sentence splitting.
    Each segment gets context from the previous segment prepended (sliding window).
    """
    if not text.strip():
        return []

    # Try splitting on double newlines
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(paras) <= 1:
        # Flat text — split by sentences
        paras = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]

    # Re-chunk so each chunk is ~target_words
    chunks: list[str] = []
    current: list[str] = []
    count = 0
    for para in paras:
        wc = len(para.split())
        if count + wc > target_words and current:
            chunks.append(" ".join(current))
            current = [para]
            count = wc
        else:
            current.append(para)
            count += wc
    if current:
        chunks.append(" ".join(current))

    return [c for c in chunks if c.strip()]


def make_documents(video_id: str, title: str, text: str, source_file: str) -> list[dict]:
    """
    Build the list of document dicts for all three levels.
    """
    docs = []
    base_meta = {"video_id": video_id, "source_file": source_file}

    # ── Level 1: summary ──────────────────────────────────────────────────────
    summary_text = f"{title}\n\n{text[:SUMMARY_CHARS]}"
    docs.append(
        {
            "content_type": "transcript_video",
            "source_id": f"transcript:{video_id}:summary",
            "title": title,
            "text": summary_text,
            "text_hash": text_hash(summary_text),
            "metadata": {**base_meta, "level": 1},
            "is_published": True,
        }
    )

    # ── Level 2: sections (~500 words each) ──────────────────────────────────
    sections = split_into_sections(text, SECTION_WORDS)
    for i, section_text in enumerate(sections):
        section_full = f"{title} — Section {i+1}\n\n{section_text}"
        docs.append(
            {
                "content_type": "transcript_section",
                "source_id": f"transcript:{video_id}:s{i}",
                "title": f"{title} — Section {i+1}",
                "text": section_full,
                "text_hash": text_hash(section_full),
                "metadata": {**base_meta, "level": 2, "section_index": i, "total_sections": len(sections)},
                "is_published": True,
            }
        )

    # ── Level 3: paragraphs (~150 words each, sliding window) ────────────────
    paragraphs = split_into_paragraphs(text, PARA_WORDS)
    for j, para_text in enumerate(paragraphs):
        # Sliding window: prepend previous paragraph as context
        if j > 0:
            context = paragraphs[j - 1]
            full_text = f"[Context: {context}]\n\n{para_text}"
        else:
            full_text = para_text

        docs.append(
            {
                "content_type": "transcript_paragraph",
                "source_id": f"transcript:{video_id}:p{j}",
                "title": f"{title} — Para {j+1}",
                "text": full_text,
                "text_hash": text_hash(full_text),
                "metadata": {**base_meta, "level": 3, "para_index": j, "total_paras": len(paragraphs)},
                "is_published": True,
            }
        )

    return docs


UPSERT_SQL = """
INSERT INTO brain_documents
    (content_type, source_id, title, text, text_hash, metadata, is_published)
VALUES %s
ON CONFLICT (content_type, source_id) DO UPDATE SET
    title             = EXCLUDED.title,
    text              = EXCLUDED.text,
    text_hash         = EXCLUDED.text_hash,
    metadata          = EXCLUDED.metadata,
    is_published      = EXCLUDED.is_published,
    updated_at        = NOW()
WHERE brain_documents.text_hash <> EXCLUDED.text_hash
"""


def upsert_batch(cur, docs: list[dict]) -> int:
    """Insert/update a batch of document dicts. Returns rows processed."""
    rows = [
        (
            d["content_type"],
            d["source_id"],
            d["title"],
            d["text"],
            d["text_hash"],
            json.dumps(d["metadata"]),
            d["is_published"],
        )
        for d in docs
    ]
    execute_values(cur, UPSERT_SQL, rows)
    return len(rows)


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    transcript_dir = Path(TRANSCRIPTS_DIR)
    files = sorted(f for f in transcript_dir.iterdir() if f.suffix == ".json" and f.name != ".claude-flow")
    total_files = len(files)
    print(f"Found {total_files} transcript files in {TRANSCRIPTS_DIR}")

    conn = psycopg2.connect(DB_URL)
    conn.autocommit = False
    cur = conn.cursor()

    stats = {
        "files_processed": 0,
        "files_skipped_empty": 0,
        "files_errored": 0,
        "docs_upserted": 0,
        "docs_skipped": 0,
    }

    pending_docs: list[dict] = []
    flush_every = BATCH_SIZE  # flush DB every N files

    def flush(docs):
        if not docs:
            return 0
        n = upsert_batch(cur, docs)
        conn.commit()
        return n

    for idx, fpath in enumerate(files, 1):
        fname = fpath.name
        video_id, title = parse_filename(fname)
        if not video_id:
            print(f"  [WARN] Could not extract video_id from: {fname}")
            stats["files_errored"] += 1
            continue

        text = load_transcript(str(fpath))
        if text is None:
            stats["files_errored"] += 1
            continue

        if not text.strip():
            print(f"  [SKIP] Empty transcript: {fname}")
            stats["files_skipped_empty"] += 1
            continue

        docs = make_documents(video_id, title, text, fname)
        pending_docs.extend(docs)
        stats["files_processed"] += 1

        # Flush periodically
        if stats["files_processed"] % flush_every == 0:
            n = flush(pending_docs)
            stats["docs_upserted"] += n
            pending_docs.clear()
            pct = idx / total_files * 100
            print(
                f"  [{idx}/{total_files}  {pct:.0f}%]  "
                f"files={stats['files_processed']}  "
                f"docs_upserted={stats['docs_upserted']}"
            )

    # Final flush
    if pending_docs:
        n = flush(pending_docs)
        stats["docs_upserted"] += n

    cur.close()
    conn.close()

    print("\n" + "=" * 60)
    print("DONE")
    print(f"  Files processed  : {stats['files_processed']}")
    print(f"  Files skipped    : {stats['files_skipped_empty']} (empty transcript)")
    print(f"  Files errored    : {stats['files_errored']}")
    print(f"  Docs upserted    : {stats['docs_upserted']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
