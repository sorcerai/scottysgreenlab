"""Scottynizer: Transform AI-generated articles into Scotty's authentic voice.

This module applies Scotty's real speech patterns, vocabulary, and rhythm
to ClawRank-generated articles. It's the final voice pass before publication.

Based on analysis of 359 TikTok transcripts (1,043,425 characters).
"""
import json
import re
import subprocess
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# ── AI Slop Patterns ──────────────────────────────────────────────
# Phrases that scream "AI wrote this" — kill on sight
AI_SLOP_PHRASES = [
    # Corporate/academic bloat
    "comprehensive guide", "in-depth guide", "ultimate guide",
    "it's important to note", "it's worth noting", "it should be noted",
    "at the end of the day", "in today's world", "in today's age",
    "when it comes to", "in terms of", "with that being said",
    "having said that", "that being said",
    # AI favorite verbs
    "delve", "delves", "delving", "delved",
    "navigate", "navigating", "navigates",
    "leverage", "leveraging", "leveraged",
    "streamline", "streamlined", "streamlining",
    "harness", "harnessing", "harnessed",
    "foster", "fostering", "fostered",
    "embark", "embarking", "embarked",
    "unpack", "unpacking", "unpacked",
    "unravel", "unraveling", "unraveled",
    # AI favorite nouns/adjectives
    "landscape", "realm", "paradigm", "synergy",
    "game-changer", "game changer", "cutting-edge", "cutting edge",
    "robust", "holistic", "myriad",
    "plethora", "multifaceted", "nuanced",
    "pivotal", "cornerstone", "tapestry",
    "bustling", "vibrant", "thriving",
    # AI structural tells
    "let's dive in", "let's dive into", "deep dive into",
    "without further ado", "buckle up",
    "the bottom line is", "here's the thing",
    "in conclusion", "to sum up", "to summarize",
    "in a nutshell", "all in all",
    # Filler hedging
    "essentially", "fundamentally", "arguably",
    "interestingly", "remarkably", "notably",
    "crucially", "importantly", "significantly",
]

# ── Scotty's Vocabulary Substitutions ─────────────────────────────
# Replace generic/formal words with how Scotty actually talks
SCOTTY_SUBS = [
    # Formality downgrades
    (r"\butilize\b", "use"),
    (r"\butilizing\b", "using"),
    (r"\bpurchase\b", "buy"),
    (r"\bpurchasing\b", "buying"),
    (r"\bcommence\b", "start"),
    (r"\bcommencing\b", "starting"),
    (r"\bfacilitate\b", "help"),
    (r"\bfacilitating\b", "helping"),
    (r"\bimplement\b", "do"),
    (r"\bimplementing\b", "doing"),
    (r"\bsubsequently\b", "then"),
    (r"\bprior to\b", "before"),
    (r"\bin order to\b", "to"),
    (r"\bdue to the fact that\b", "because"),
    (r"\bin the event that\b", "if"),
    (r"\bat this point in time\b", "now"),
    (r"\bon a daily basis\b", "every day"),
    (r"\ba significant amount of\b", "a lot of"),
    (r"\bin close proximity to\b", "near"),
    (r"\bhas the ability to\b", "can"),
    (r"\bin spite of the fact that\b", "even though"),
    # Scotty-isms
    (r"\bvegetable garden\b", "garden"),
    (r"\bthe bacteria\b", "the bugs"),  # Scotty often calls bacteria "bugs"
    (r"\bmicroorganisms\b", "microbes"),
    (r"\bdecomposition\b", "decay"),
    (r"\bdecompose\b", "break down"),
    (r"\bdecomposes\b", "breaks down"),
    (r"\bNutrient-dense\b", "Nutrient-dense"),  # keep as-is, Scotty uses this
]

# ── AI Structural Patterns ────────────────────────────────────────
# Regex patterns for AI writing structure
AI_STRUCTURE_PATTERNS = [
    # "Not only X, but also Y" — AI loves this
    (r"Not only (.*?), but also", r"\1, and"),
    # "Whether you're a X or a Y" — AI demographic hedging
    (r"Whether you're a .+? or a .+?,\s*", ""),
    # Em dash overuse — Scotty uses them sparingly
    # (handled separately)
    # Colon-list pattern "There are several key factors:"
    (r"There are (?:several|many|a number of) (?:key |important |critical )?(?:factors|reasons|benefits|ways|steps):", "Here's what matters:"),
    # "X is a Y that Z" definition pattern
    # (too broad to regex, handled in LLM pass)
]

# ── Sentence Rhythm ───────────────────────────────────────────────
# Scotty's cadence: 16 words avg, 32% short (≤8), 42% medium (9-20), 26% long (>20)
# If we see 3+ long sentences in a row, break them up


def strip_ai_slop(text: str) -> str:
    """Remove AI-characteristic phrases and patterns."""
    result = text
    for phrase in AI_SLOP_PHRASES:
        # Case-insensitive removal, handling sentence-start capitalization
        pattern = re.compile(re.escape(phrase), re.IGNORECASE)
        result = pattern.sub("", result)

    # Clean up double spaces, orphaned commas, etc.
    result = re.sub(r"  +", " ", result)
    result = re.sub(r" ,", ",", result)
    result = re.sub(r",\s*,", ",", result)
    result = re.sub(r"\.\s*\.", ".", result)
    result = re.sub(r"^\s*,\s*", "", result, flags=re.MULTILINE)
    return result


def apply_scotty_subs(text: str) -> str:
    """Replace formal/generic words with Scotty's vocabulary."""
    result = text
    for pattern, replacement in SCOTTY_SUBS:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    return result


def apply_structure_patterns(text: str) -> str:
    """Fix AI structural writing patterns."""
    result = text
    for pattern, replacement in AI_STRUCTURE_PATTERNS:
        result = re.sub(pattern, replacement, result)
    return result


def fix_em_dashes(text: str) -> str:
    """Reduce em dash overuse. Scotty uses them sparingly."""
    # Count em dashes
    em_dash_count = text.count("—")
    word_count = len(text.split())

    # More than 1 em dash per 300 words is too many
    max_allowed = max(2, word_count // 300)
    if em_dash_count <= max_allowed:
        return text

    # Replace excess em dashes with periods or commas
    parts = text.split("—")
    result_parts = [parts[0]]
    dash_used = 0
    for part in parts[1:]:
        if dash_used < max_allowed:
            result_parts.append("—" + part)
            dash_used += 1
        else:
            # Replace with period if the preceding text could end a sentence
            stripped_prev = result_parts[-1].rstrip()
            if stripped_prev and stripped_prev[-1].isalpha():
                result_parts.append(". " + part.lstrip().capitalize() if part.strip() else part)
            else:
                result_parts.append(", " + part.lstrip())

    return "".join(result_parts)


def check_rhythm(text: str) -> list[str]:
    """Analyze sentence rhythm and return warnings for AI-like patterns."""
    warnings = []
    sentences = re.split(r'(?<=[.!?])\s+', text)
    long_streak = 0
    for s in sentences:
        words = len(s.split())
        if words > 25:
            long_streak += 1
            if long_streak >= 3:
                warnings.append(f"3+ long sentences in a row near: '{s[:60]}...'")
        else:
            long_streak = 0
    return warnings


def scottynize_with_llm(text: str, voice_profile_path: Path | None = None) -> str:
    """Run the article through an LLM pass with Scotty's voice rules.

    This is the deep pass — the LLM rewrites sections that sound too formal,
    too academic, or too AI-generated while preserving all facts and citations.
    """
    voice_path = voice_profile_path or (PROJECT_ROOT / "src" / "data" / "scotty-voice-profile.md")
    voice_text = voice_path.read_text()[:8000]  # First 8K chars of voice profile

    prompt = f"""You are rewriting an article to sound exactly like Scotty from Scotty's Gardening Lab.

SCOTTY'S VOICE (from 359 TikTok transcripts):
- Average sentence: 16 words. Short claim, medium explanation, punchy payoff.
- Top words: bacteria (737x), pile (712x), soil (565x), y'all (462x), compost (456x), gut (416x)
- Signature phrases: "a little bit" (432x), "the decay cycle" (65x), "your gut bacteria" (42x)
- Opens with declarations or observations, not greetings
- Says "y'all" naturally, "basically", "pretty much", "a bunch of"
- Calls bacteria "bugs" sometimes
- References "the farmers market", "Spring Branch", "Houston"
- Teaching cadence: states a fact, explains the mechanism, delivers the payoff
- NEVER sounds like a blog. Sounds like a farmer explaining science at the market.
- Low-pressure closer: "anyway, thanks y'all" energy
- Uses "I" and "we" — first person, personal experience
- Specific, not vague. Numbers, not adjectives.

RULES:
1. Keep ALL facts, citations, data points, internal links, and direct answer blocks intact
2. Keep ALL section headings (H1, H2, H3) intact
3. Keep the FAQ section intact (questions and answers)
4. Remove any remaining AI slop phrases
5. Make every sentence sound like something Scotty would actually say on TikTok
6. Short sentences between longer ones. Never 3+ long sentences in a row.
7. Add "y'all" 2-3 times naturally (not forced)
8. Replace formal transitions with natural ones ("Now here's the thing", "Look", "So")
9. Keep the Spring Branch / Houston / Zone 9a references
10. Product mentions should feel organic, not salesy
11. Do NOT add new facts or remove existing ones
12. Do NOT change the JSON structure — only modify the "body" text content
13. Return ONLY the rewritten body text, nothing else

ARTICLE TO SCOTTYNIZE:
{text}

Return the rewritten article body only. No JSON wrapping, no explanation."""

    try:
        # Use gemini -p for the rewrite pass
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write(prompt)
            f.flush()
            temp_path = f.name

        result = subprocess.run(
            ["gemini", "-p", prompt],
            capture_output=True, text=True, timeout=300,
            cwd=str(PROJECT_ROOT),
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        return text  # Fallback to original on failure
    except Exception:
        return text


def strip_cli_noise(text: str) -> str:
    """Remove gemini/claude CLI warnings that leak into output."""
    # MCP warnings from gemini CLI
    text = re.sub(r"MCP issues detected\..*?\n", "", text)
    text = re.sub(r"Run /mcp list for status\.?\s*", "", text)
    # Strip leading whitespace/newlines after cleanup
    text = text.lstrip("\n ")
    return text


def post_llm_cleanup(text: str) -> str:
    """Fix issues that survive or get reintroduced by the LLM rewrite pass."""
    # 1. Remove [DIRECT ANSWER] blocks (GEO markup, not for display)
    text = re.sub(r"> \[DIRECT ANSWER\]\n(?:> .*\n?)*", "", text)
    text = re.sub(r"\[DIRECT ANSWER\]", "", text)

    # 2. Replace self-citations ("According to Scotty's Gardening Lab")
    text = re.sub(
        r"[Aa]ccording to Scotty'?s? (?:Gardening|Green) Lab,?\s*",
        "",
        text,
    )

    # 3. Strip markdown bullet markers (mdToHtml doesn't render lists)
    text = re.sub(r"^- ", "", text, flags=re.MULTILINE)

    # 4. Strip markdown code fences that wrap the whole body
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n", "", text)
        text = re.sub(r"\n```\s*$", "", text)

    # 5. Clean up triple+ blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text


def scottynize(article_json: dict, *, llm_pass: bool = True) -> dict:
    """Full Scottynizer pipeline.

    1. Strip AI slop phrases
    2. Apply Scotty vocabulary substitutions
    3. Fix AI structural patterns
    4. Fix em dash overuse
    5. (Optional) LLM deep rewrite pass
    6. Check rhythm warnings

    Args:
        article_json: The stage-12 content_draft output (with "body" key)
        llm_pass: Whether to run the expensive LLM rewrite (default True)

    Returns:
        Modified article_json with scottynized body
    """
    body = article_json.get("body", "")
    if not body:
        return article_json

    # Step 0: Strip gemini CLI noise (MCP warnings, etc.)
    body = strip_cli_noise(body)

    # Step 1: Strip AI slop
    body = strip_ai_slop(body)

    # Step 2: Scotty vocabulary
    body = apply_scotty_subs(body)

    # Step 3: Structural patterns
    body = apply_structure_patterns(body)

    # Step 4: Em dashes
    body = fix_em_dashes(body)

    # Step 5: LLM deep rewrite
    if llm_pass:
        body = scottynize_with_llm(body)

    # Step 6: Post-LLM cleanup (things the LLM might reintroduce)
    body = post_llm_cleanup(body)

    # Step 7: Check rhythm (warnings only, for logging)
    warnings = check_rhythm(body)

    result = dict(article_json)
    result["body"] = body
    result["scottynizer_warnings"] = warnings
    result["scottynized"] = True
    return result


def scottynize_file(input_path: str, output_path: str | None = None, *, llm_pass: bool = True) -> str:
    """Scottynize a stage-12 JSON artifact file.

    Args:
        input_path: Path to the content_draft JSON
        output_path: Where to write the result (default: same dir, -scottynized suffix)
        llm_pass: Whether to run the LLM rewrite

    Returns:
        Path to the output file
    """
    inp = Path(input_path)
    raw = inp.read_text()

    # Handle markdown code fence wrapping
    if raw.startswith("```"):
        raw = re.sub(r"^```\w*\n", "", raw)
        raw = re.sub(r"\n```\s*$", "", raw)

    article = json.loads(raw)
    result = scottynize(article, llm_pass=llm_pass)

    out = Path(output_path) if output_path else inp.with_name(inp.stem + "-scottynized.json")
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    return str(out)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Scottynize a ClawRank article")
    parser.add_argument("input", help="Path to stage-12 JSON artifact")
    parser.add_argument("-o", "--output", help="Output path (default: input-scottynized.json)")
    parser.add_argument("--no-llm", action="store_true", help="Skip the LLM rewrite pass")
    args = parser.parse_args()
    out = scottynize_file(args.input, args.output, llm_pass=not args.no_llm)
    print(f"Scottynized: {out}")
