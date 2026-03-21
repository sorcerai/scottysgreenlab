import pytest


def test_parse_args_mode_auto():
    from scripts.clawrank.run import parse_args
    args = parse_args(["--mode", "auto"])
    assert args.mode == "auto"


def test_parse_args_mode_research_with_keyword():
    from scripts.clawrank.run import parse_args
    args = parse_args(["--mode", "research", "--keyword", "hot composting houston"])
    assert args.mode == "research"
    assert args.keyword == "hot composting houston"


def test_parse_args_backend_default():
    from scripts.clawrank.run import parse_args
    args = parse_args(["--mode", "auto"])
    assert args.backend == "gemini"


def test_parse_args_from_to_stage():
    from scripts.clawrank.run import parse_args
    args = parse_args(["--mode", "batch", "--from-stage", "12", "--to-stage", "23"])
    assert args.from_stage == 12
    assert args.to_stage == 23


def test_parse_args_dry_run():
    from scripts.clawrank.run import parse_args
    args = parse_args(["--mode", "auto", "--dry-run"])
    assert args.dry_run is True


def test_parse_args_verbose():
    from scripts.clawrank.run import parse_args
    args = parse_args(["--mode", "auto", "--verbose"])
    assert args.verbose is True


def test_parse_args_dry_run_default_false():
    from scripts.clawrank.run import parse_args
    args = parse_args(["--mode", "auto"])
    assert args.dry_run is False
