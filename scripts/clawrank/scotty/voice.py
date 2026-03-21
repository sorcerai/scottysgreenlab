"""
scotty/voice.py — Load Scotty's voice profile and format it as a prompt block.

The voice profile is a 59KB markdown file extracted from 359 TikTok transcripts.
This module parses the relevant sections into structured data usable by LLM prompts.
"""

from __future__ import annotations

import re
from pathlib import Path


# ---------------------------------------------------------------------------
# Hardcoded lists
# ---------------------------------------------------------------------------

BANNED_PHRASES: list[str] = [
    "delve",
    "landscape",
    "leverage",
    "comprehensive guide",
    "game-changer",
    "synergy",
    "cutting-edge",
    "robust",
    "streamline",
    "paradigm",
    "holistic approach",
]

# Tone rules distilled from the "ACTIONABLE VOICE GUIDE" and teaching-style sections.
TONE_RULES: list[str] = [
    "Conversational-scientific blend: technical terms (prokaryote, thermophilic, lateral gene transfer) explained in plain Texas vernacular.",
    "Texas dialect: use 'y'all' throughout; Southern casual pace; farmers-market culture.",
    "First-person experience: 'I found...', 'In my garden...', 'From talking to customers at the market...' — not generic authority.",
    "Open with the point, not a greeting: lead with the concept or problem, not 'Hey guys, today I'm going to talk about...'",
    "Use 'a little bit' constantly — it softens technical content and creates intimacy.",
    "Personalize with 'your': your soil, your gut bacteria, your garden — never clinical distance.",
    "Name the villain before the hero: chemical fertilizers / synthetic inputs -> dead soil; antibiotics / tap water -> damaged gut.",
    "Explain the mechanism, not just the tip: always go one level deeper into WHY via soil biology or gut biology.",
    "'Living' is the most important adjective: living soil, living food, living bacteria, active ferment.",
    "Use 'basically' as a pivot into the simple explanation after a complex setup.",
    "Sign off casual and warm: 'Anyway, thanks y'all.' — never a hard sales pitch.",
    "Failure = learning; imperfection = authenticity: perfectionism is absent from this brand.",
    "Rhythm template: [Short claim 5-8 words] -> [Medium mechanism 15-20 words] -> [What this means for you 10-15 words] -> [Optional soft CTA or sign-off].",
    "Humor is self-deprecating and observational, not performative.",
    "Wonder level is high: genuine astonishment at microbial processes ('just mind-blowing').",
]

# Key concepts central to Scotty's worldview.
KEY_CONCEPTS: list[str] = [
    "living soil",
    "prokaryotic association",
    "law of returns",
    "lacto-fermentation",
    "nutrient density",
    "regenerative",
    "decay cycle",
    "beneficial bacteria",
    "gut-soil connection",
    "compost",
    "fermented foods",
    "Albert Howard",
    "Indore method",
]


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def _extract_vocabulary(text: str) -> list[dict]:
    """
    Parse the VOCABULARY FINGERPRINT section.

    Lines look like:  `bacteria`: 737
    Returns top 20 as list of {word, count}.
    """
    vocab: list[dict] = []
    # Match backtick-quoted word followed by colon and integer.
    pattern = re.compile(r"`([^`]+)`\s*:\s*(\d+)")
    for match in pattern.finditer(text):
        word = match.group(1).strip()
        count = int(match.group(2))
        vocab.append({"word": word, "count": count})
        if len(vocab) >= 20:
            break
    return vocab


def _extract_signature_phrases(text: str) -> list[str]:
    """
    Extract quoted phrases from the RECURRING PHRASES section and the
    SIGNATURE PHRASES section.  Collect any double-quoted string that looks
    like a real phrase (>= 3 words or well-known short phrases).
    """
    phrases: list[str] = []
    seen: set[str] = set()

    # Pull every "..." quoted string from the document.
    for match in re.finditer(r'"([^"]{5,80})"', text):
        phrase = match.group(1).strip()
        if phrase not in seen:
            seen.add(phrase)
            phrases.append(phrase)

    # Also grab the 3-word / 4-word pattern lines explicitly (unquoted):
    #   "a little bit" — 432x
    for match in re.finditer(r'^  "([^"]+)" — \d+x', text, re.MULTILINE):
        phrase = match.group(1).strip()
        if phrase not in seen:
            seen.add(phrase)
            phrases.append(phrase)

    return phrases[:40]  # cap at 40 to keep prompt block manageable


def _extract_tone_rules_from_text(text: str) -> list[str]:
    """
    Pull the numbered rules from the '20. ACTIONABLE VOICE GUIDE' section.
    Falls back to the hardcoded TONE_RULES if the section is missing/malformed.
    """
    rules: list[str] = []

    # Find the section after "Writing in Scotty's Voice"
    section_match = re.search(
        r"Writing in Scotty'?s Voice.*?(?=###|\Z)", text, re.DOTALL | re.IGNORECASE
    )
    if section_match:
        section = section_match.group(0)
        # Each rule is a bold numbered item: **1. ...**\nBody text
        for match in re.finditer(r"\*\*\d+\.\s+([^\*]+)\*\*\s*\n([^\n]+)", section):
            title = match.group(1).strip()
            body = match.group(2).strip()
            rules.append(f"{title}: {body}")

    return rules if rules else list(TONE_RULES)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_voice_profile(path: Path) -> dict:
    """
    Parse the scotty-voice-profile.md into a structured dict.

    Keys:
        vocabulary      — list of {word, count} (top 20)
        banned_phrases  — list[str] (hardcoded AI-slop blocklist)
        tone_rules      — list[str] (writing rules from the profile)
        signature_phrases — list[str] (quoted phrases extracted from profile)
        key_concepts    — list[str] (core domain concepts)
        raw_text        — str (full markdown text)
    """
    raw_text = Path(path).read_text(encoding="utf-8")

    vocabulary = _extract_vocabulary(raw_text)
    signature_phrases = _extract_signature_phrases(raw_text)
    tone_rules = _extract_tone_rules_from_text(raw_text)

    return {
        "vocabulary": vocabulary,
        "banned_phrases": list(BANNED_PHRASES),
        "tone_rules": tone_rules,
        "signature_phrases": signature_phrases,
        "key_concepts": list(KEY_CONCEPTS),
        "raw_text": raw_text,
    }


def build_voice_block(profile: dict) -> str:
    """
    Format the voice profile dict into a markdown prompt block for LLM injection.

    Sections:
        ## Scotty's Voice Rules
        ## Tone
        ## Key Vocabulary
        ## Key Concepts
        ## BANNED Phrases
        ## Signature Phrases
    """
    lines: list[str] = []

    lines.append("## Scotty's Voice Rules")
    lines.append("")
    for i, rule in enumerate(profile.get("tone_rules", []), 1):
        lines.append(f"{i}. {rule}")
    lines.append("")

    lines.append("## Tone")
    lines.append("")
    lines.append(
        "Conversational-scientific. Texas identity baked in — y'all, farmers market culture, "
        "backyard chickens, Houston. Explain mechanisms, not just tips. "
        "Short claim → medium explanation → consequence. Self-deprecating humor. High wonder."
    )
    lines.append("")

    lines.append("## Key Vocabulary")
    lines.append("")
    vocab = profile.get("vocabulary", [])
    if vocab:
        vocab_str = ", ".join(
            f"{v['word']} ({v['count']})" for v in vocab
        )
        lines.append(f"Top words by frequency: {vocab_str}")
    lines.append("")

    lines.append("## Key Concepts")
    lines.append("")
    concepts = profile.get("key_concepts", [])
    for concept in concepts:
        lines.append(f"- {concept}")
    lines.append("")

    lines.append("## BANNED Phrases")
    lines.append("")
    lines.append("Never use any of these — they sound like generic AI slop, not Scotty:")
    lines.append("")
    for phrase in profile.get("banned_phrases", []):
        lines.append(f"- {phrase}")
    lines.append("")

    lines.append("## Signature Phrases")
    lines.append("")
    lines.append("Use these naturally where appropriate:")
    lines.append("")
    for phrase in profile.get("signature_phrases", [])[:20]:
        lines.append(f'- "{phrase}"')
    lines.append("")

    return "\n".join(lines)
