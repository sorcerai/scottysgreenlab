import pytest
from pathlib import Path

VOICE_PROFILE_PATH = Path("src/data/scotty-voice-profile.md")

def test_voice_profile_exists():
    assert VOICE_PROFILE_PATH.exists()

def test_load_voice_returns_dict():
    from scripts.clawrank.scotty.voice import load_voice_profile
    profile = load_voice_profile(VOICE_PROFILE_PATH)
    assert isinstance(profile, dict)

def test_voice_has_banned_phrases():
    from scripts.clawrank.scotty.voice import load_voice_profile
    profile = load_voice_profile(VOICE_PROFILE_PATH)
    assert "banned_phrases" in profile
    assert len(profile["banned_phrases"]) > 0

def test_voice_has_tone_rules():
    from scripts.clawrank.scotty.voice import load_voice_profile
    profile = load_voice_profile(VOICE_PROFILE_PATH)
    assert "tone_rules" in profile

def test_build_voice_block_returns_string():
    from scripts.clawrank.scotty.voice import load_voice_profile, build_voice_block
    profile = load_voice_profile(VOICE_PROFILE_PATH)
    block = build_voice_block(profile)
    assert isinstance(block, str)
    assert len(block) > 100
    assert "y'all" in block.lower() or "bacteria" in block.lower()
