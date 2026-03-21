"""Hybrid LLM Adapter for ClawRank.

Routes LLM calls through two backends:
- Gemini CLI (`gemini -p`) for lightweight stages (1-11, 14, 16-19, 21-23)
- Claude CLI (`claude -p`) for heavy content generation stages (12, 13, 15, 20)

ACPX can't handle large prompts as CLI arguments (exit code 5 / OS arg limit).
Claude CLI accepts prompts via stdin, bypassing this limit.

Usage::

    from scripts.clawrank.core.acpx_adapter import AcpxLLMAdapter, check_backends_installed

    status = check_backends_installed()
    if not status["claude_cli"]:
        print("Claude CLI required: https://docs.anthropic.com/claude-code")
        sys.exit(1)

    llm = AcpxLLMAdapter(backend="gemini", heavy_backend="claude", session_prefix="clawrank")
    response = llm.complete(
        system_prompt="You are an SEO expert.",
        user_prompt="Analyze this niche: cannabis growing",
        stage=1,
    )
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Valid ACPX backends
VALID_BACKENDS = {"claude", "codex", "gemini"}

# Timeout per stage call (seconds)
DEFAULT_TIMEOUT = 300
LONG_STAGE_TIMEOUT = 900  # Content generation stages need more time

# Heavy stages routed to heavy_backend (claude) — large prompts, long outputs
LONG_STAGES = {12, 13, 15, 20}


def check_acpx_installed() -> bool:
    """Check if ACPX CLI is installed and accessible."""
    try:
        result = subprocess.run(
            ["acpx", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False
    except subprocess.TimeoutExpired:
        return False


def check_claude_cli_installed() -> bool:
    """Check if Claude Code CLI is installed and accessible."""
    try:
        result = subprocess.run(
            ["claude", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False
    except subprocess.TimeoutExpired:
        return False


def check_backends_installed() -> dict[str, bool]:
    """Check which LLM backends are available."""
    return {
        "acpx": check_acpx_installed(),
        "claude_cli": check_claude_cli_installed(),
    }


def get_acpx_version() -> str:
    """Return the installed ACPX version string, or empty string if not installed."""
    try:
        result = subprocess.run(
            ["acpx", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return ""


class AcpxLLMAdapter:
    """Hybrid LLM adapter: per-stage backend routing + GPU model support.

    Light stages (1-11, 14, 16-19, 21-23) use `backend` (default: gemini).
    Heavy stages (12, 13, 15, 20) use `heavy_backend` (default: claude).

    Each pipeline stage gets its own named ACPX session so conversation
    history is preserved within a stage (useful for retries and
    multi-turn refinement stages like 13 and 17-18).

    GPU model calls (intent classifier, query fanout, sentiment, reranker)
    are handled via `call_gpu_model()` with graceful degradation on failure.
    """

    def __init__(
        self,
        backend: str = "gemini",
        heavy_backend: str = "claude",  # backend for LONG_STAGES
        session_prefix: str = "clawrank",
        max_retries: int = 3,
        retry_delay: float = 2.0,
        claude_model: str = "",
    ) -> None:
        if backend not in VALID_BACKENDS:
            raise ValueError(
                f"Invalid ACPX backend: {backend}. Must be one of: {VALID_BACKENDS}"
            )
        if heavy_backend not in VALID_BACKENDS:
            raise ValueError(
                f"Invalid heavy_backend: {heavy_backend}. Must be one of: {VALID_BACKENDS}"
            )
        self.backend = backend
        self.heavy_backend = heavy_backend
        self.session_prefix = session_prefix
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.claude_model = claude_model  # e.g. "sonnet" — empty = default

        # Detect available backends at init
        self._has_acpx = check_acpx_installed()
        self._has_claude_cli = check_claude_cli_installed()

        if not self._has_acpx and not self._has_claude_cli:
            raise RuntimeError(
                "No LLM backend available. Install ACPX (npm install -g acpx) "
                "or Claude CLI (https://docs.anthropic.com/claude-code)."
            )

        if not self._has_claude_cli:
            logger.warning(
                "Claude CLI not found — heavy stages (%s) will fall back to ACPX "
                "(may fail on large prompts)",
                LONG_STAGES,
            )

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        stage: int,
        max_tokens: int = 4096,
        no_wait: bool = False,
    ) -> str:
        """Run a completion through the appropriate backend.

        Routes to heavy_backend for LONG_STAGES, backend for everything else.

        Args:
            system_prompt: The system-level instructions.
            user_prompt: The user message / task.
            stage: Pipeline stage number (used for routing + session naming).
            max_tokens: Max tokens for the response (advisory).
            no_wait: If True, fire-and-forget (for noncritical stages).

        Returns:
            The extracted text response from the LLM.

        Raises:
            AcpxError: If the backend fails after all retries.
        """
        effective_backend = self.heavy_backend if stage in LONG_STAGES else self.backend

        if effective_backend == "gemini":
            return self._complete_via_gemini_cli(
                system_prompt, user_prompt, stage, max_tokens
            )
        elif effective_backend == "claude":
            if self._has_claude_cli:
                return self._complete_via_claude_cli(
                    system_prompt, user_prompt, stage, max_tokens
                )
            elif self._has_acpx:
                return self._complete_via_acpx(
                    system_prompt, user_prompt, stage, max_tokens, no_wait
                )
            else:
                raise AcpxError(
                    "Claude CLI not available and ACPX not installed. "
                    "Install Claude CLI: https://docs.anthropic.com/claude-code"
                )
        elif self._has_acpx:
            return self._complete_via_acpx(
                system_prompt, user_prompt, stage, max_tokens, no_wait
            )
        else:
            return self._complete_via_claude_cli(
                system_prompt, user_prompt, stage, max_tokens
            )

    # ------------------------------------------------------------------
    # GPU model backend (DEJAN servers: reranker, intent, sentiment, etc.)
    # ------------------------------------------------------------------

    def call_gpu_model(self, url: str, payload: dict, timeout: float = 10.0) -> dict | None:
        """HTTP POST to GPU model endpoint. Returns None on failure (graceful degradation).

        Used for DEJAN server calls: intent classifier, query fanout,
        sentiment analysis, and the Qwen3 reranker.

        Args:
            url: Full HTTP endpoint URL (e.g. "http://100.66.51.21:8788/rerank").
            payload: JSON-serializable request body.
            timeout: Request timeout in seconds (default: 10.0).

        Returns:
            Parsed JSON response dict, or None if the call fails for any reason.
        """
        import requests
        try:
            resp = requests.post(url, json=payload, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Gemini CLI backend (direct, no ACPX needed)
    # ------------------------------------------------------------------

    def _complete_via_gemini_cli(
        self,
        system_prompt: str,
        user_prompt: str,
        stage: int,
        max_tokens: int,
    ) -> str:
        """Run a completion via `gemini -p` (direct CLI, no ACPX).

        Gemini CLI works clean — no hooks, no CLAUDE.md contamination.
        Prompt passed as -p argument. Output as JSON with 'response' field.
        """
        combined_prompt = f"<system>\n{system_prompt}\n</system>\n\n{user_prompt}"
        timeout = LONG_STAGE_TIMEOUT if stage in LONG_STAGES else DEFAULT_TIMEOUT

        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(
                    "Gemini CLI call: stage=%d attempt=%d prompt_len=%d",
                    stage, attempt, len(combined_prompt),
                )

                cmd = [
                    "gemini",
                    "-p", combined_prompt,
                    "--output-format", "json",
                ]

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )

                if result.returncode != 0:
                    stderr = result.stderr.strip()
                    logger.warning(
                        "Gemini CLI exit code %d (attempt %d/%d): %s",
                        result.returncode, attempt, self.max_retries, stderr,
                    )
                    last_error = AcpxError(
                        f"Gemini CLI exit code {result.returncode}: {stderr}"
                    )
                    if attempt < self.max_retries:
                        time.sleep(self.retry_delay * attempt)
                    continue

                response = self._extract_gemini_cli_response(result.stdout)
                if not response.strip():
                    logger.warning(
                        "Gemini CLI empty response (attempt %d/%d)",
                        attempt, self.max_retries,
                    )
                    last_error = AcpxError("Empty response from Gemini CLI")
                    if attempt < self.max_retries:
                        time.sleep(self.retry_delay * attempt)
                    continue

                logger.info(
                    "Gemini CLI response: %d chars from stage %d",
                    len(response), stage,
                )
                return response

            except subprocess.TimeoutExpired:
                logger.warning(
                    "Gemini CLI timed out after %ds (attempt %d/%d)",
                    timeout, attempt, self.max_retries,
                )
                last_error = AcpxError(f"Gemini CLI timed out after {timeout}s")
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay * attempt)

        raise last_error or AcpxError("Gemini CLI failed after all retries")

    def _extract_gemini_cli_response(self, raw_output: str) -> str:
        """Extract text from `gemini -p --output-format json` output.

        Output format: {"session_id":"...","response":"<text>","stats":{...}}
        May have MCP warning prefix before the JSON.
        """
        raw = raw_output.strip()
        if not raw:
            return ""

        # Strip MCP warning prefix if present
        json_start = raw.find("{")
        if json_start > 0:
            raw = raw[json_start:]

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Try last line
            for line in reversed(raw.split("\n")):
                line = line.strip()
                if not line or not line.startswith("{"):
                    continue
                try:
                    data = json.loads(line)
                    break
                except json.JSONDecodeError:
                    continue
            else:
                return raw  # Return as plain text

        if isinstance(data, dict) and "response" in data:
            return str(data["response"])

        return raw

    # ------------------------------------------------------------------
    # Claude CLI backend (for heavy stages)
    # ------------------------------------------------------------------

    def _complete_via_claude_cli(
        self,
        system_prompt: str,
        user_prompt: str,
        stage: int,
        max_tokens: int,
    ) -> str:
        """Run a completion via `claude -p` with prompt piped from stdin.

        This bypasses OS argument-length limits by writing the prompt to
        a temp file and piping it in.
        """
        combined_prompt = f"<system>\n{system_prompt}\n</system>\n\n{user_prompt}"
        timeout = LONG_STAGE_TIMEOUT

        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(
                    "Claude CLI call: stage=%d attempt=%d prompt_len=%d",
                    stage, attempt, len(combined_prompt),
                )

                # Write prompt to temp file (avoids stdin buffering issues
                # with very large prompts)
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    suffix=".txt",
                    prefix=f"clawrank-stage{stage}-",
                    delete=False,
                ) as f:
                    f.write(combined_prompt)
                    prompt_path = Path(f.name)

                try:
                    cmd = [
                        "claude",
                        "-p",
                        "--output-format", "json",
                        "--max-turns", "1",
                    ]
                    if self.claude_model:
                        cmd.extend(["--model", self.claude_model])

                    # Pipe prompt via stdin from file
                    with prompt_path.open() as stdin_file:
                        result = subprocess.run(
                            cmd,
                            stdin=stdin_file,
                            capture_output=True,
                            text=True,
                            timeout=timeout,
                        )
                finally:
                    # Clean up temp file
                    prompt_path.unlink(missing_ok=True)

                if result.returncode != 0:
                    stderr = result.stderr.strip()
                    logger.warning(
                        "Claude CLI exit code %d (attempt %d/%d): %s",
                        result.returncode, attempt, self.max_retries, stderr,
                    )
                    last_error = AcpxError(
                        f"Claude CLI exit code {result.returncode}: {stderr}"
                    )
                    if attempt < self.max_retries:
                        time.sleep(self.retry_delay * attempt)
                    continue

                response = self._extract_claude_cli_response(result.stdout)
                if not response.strip():
                    logger.warning(
                        "Claude CLI empty response (attempt %d/%d)",
                        attempt, self.max_retries,
                    )
                    last_error = AcpxError("Empty response from Claude CLI")
                    if attempt < self.max_retries:
                        time.sleep(self.retry_delay * attempt)
                    continue

                logger.info(
                    "Claude CLI response: %d chars from stage %d",
                    len(response), stage,
                )
                return response

            except subprocess.TimeoutExpired:
                logger.warning(
                    "Claude CLI timed out after %ds (attempt %d/%d)",
                    timeout, attempt, self.max_retries,
                )
                last_error = AcpxError(f"Claude CLI timed out after {timeout}s")
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay * attempt)

        raise last_error or AcpxError("Claude CLI failed after all retries")

    def _extract_claude_cli_response(self, raw_output: str) -> str:
        """Extract the text response from `claude -p --output-format json` output.

        Output format: {"type":"result","subtype":"success","result":"<text>",...}
        """
        raw = raw_output.strip()
        if not raw:
            return ""

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # If not valid JSON, try NDJSON (take last line)
            for line in reversed(raw.split("\n")):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    break
                except json.JSONDecodeError:
                    continue
            else:
                # No JSON found — return raw text stripped of ANSI
                ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
                return ansi_escape.sub("", raw)

        # Standard claude -p JSON format
        if isinstance(data, dict):
            if data.get("is_error"):
                error_msg = data.get("result", "Unknown error")
                raise AcpxError(f"Claude CLI reported error: {error_msg}")
            if "result" in data:
                return str(data["result"])

        return ""

    # ------------------------------------------------------------------
    # ACPX backend (for lightweight stages)
    # ------------------------------------------------------------------

    def _complete_via_acpx(
        self,
        system_prompt: str,
        user_prompt: str,
        stage: int,
        max_tokens: int,
        no_wait: bool,
    ) -> str:
        """Run a completion through ACPX CLI (original path)."""
        if not self._has_acpx:
            raise AcpxError(
                f"ACPX not installed and stage {stage} is not routed to Claude CLI. "
                "Install ACPX: npm install -g acpx"
            )

        session_name = f"{self.session_prefix}-stage-{stage}"
        self._ensure_session(session_name)

        combined_prompt = f"<system>\n{system_prompt}\n</system>\n\n{user_prompt}"

        cmd = [
            "acpx",
            self.backend,
            "-s", session_name,
            combined_prompt,
        ]

        timeout = LONG_STAGE_TIMEOUT if stage in LONG_STAGES else DEFAULT_TIMEOUT

        if no_wait:
            return self._fire_and_forget(cmd, stage)

        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.debug(
                    "ACPX call: backend=%s session=%s stage=%d attempt=%d",
                    self.backend, session_name, stage, attempt,
                )

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )

                if result.returncode != 0:
                    stderr = result.stderr.strip()
                    logger.warning(
                        "ACPX returned exit code %d (attempt %d/%d): %s",
                        result.returncode, attempt, self.max_retries, stderr,
                    )
                    last_error = AcpxError(
                        f"ACPX exit code {result.returncode}: {stderr}"
                    )
                    # Exit code 5 = session broken. Reset and create fresh.
                    if result.returncode == 5:
                        logger.info(
                            "Exit code 5 — resetting session %s for fresh retry",
                            session_name,
                        )
                        self.reset_session(stage)
                        self._ensure_session(session_name)
                        # Rebuild cmd with same session name (new underlying session)
                        cmd = [
                            "acpx",
                            self.backend,
                            "-s", session_name,
                            combined_prompt,
                        ]
                    if attempt < self.max_retries:
                        time.sleep(self.retry_delay * attempt)
                    continue

                response = self._extract_acpx_response(result.stdout)
                if not response.strip():
                    logger.warning(
                        "ACPX returned empty response (attempt %d/%d)",
                        attempt, self.max_retries,
                    )
                    last_error = AcpxError("Empty response from ACPX")
                    if attempt < self.max_retries:
                        time.sleep(self.retry_delay * attempt)
                    continue

                logger.debug(
                    "ACPX response: %d chars from stage %d",
                    len(response), stage,
                )
                return response

            except subprocess.TimeoutExpired:
                logger.warning(
                    "ACPX timed out after %ds (attempt %d/%d)",
                    timeout, attempt, self.max_retries,
                )
                last_error = AcpxError(f"ACPX timed out after {timeout}s")
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay * attempt)

        raise last_error or AcpxError("ACPX failed after all retries")

    # ------------------------------------------------------------------
    # ACPX helpers
    # ------------------------------------------------------------------

    def _ensure_session(self, session_name: str) -> None:
        """Create an ACPX session if it doesn't exist."""
        check = subprocess.run(
            ["acpx", self.backend, "sessions", "show", "-s", session_name],
            capture_output=True, text=True, timeout=10,
        )
        if check.returncode == 0:
            return

        logger.info("Creating ACPX session: %s", session_name)
        create = subprocess.run(
            ["acpx", self.backend, "sessions", "new", "--name", session_name],
            capture_output=True, text=True, timeout=30,
        )
        if create.returncode != 0:
            logger.warning("Session creation returned %d: %s", create.returncode, create.stderr.strip())
        else:
            logger.info("ACPX session created: %s", session_name)

    def _fire_and_forget(self, cmd: list[str], stage: int) -> str:
        """Launch ACPX in the background without waiting for output."""
        logger.info("ACPX fire-and-forget: stage %d", stage)
        try:
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return json.dumps({"status": "dispatched", "stage": stage})
        except Exception as exc:
            logger.error("ACPX fire-and-forget failed: %s", exc)
            return json.dumps({"status": "error", "stage": stage, "error": str(exc)})

    def _extract_acpx_response(self, raw_output: str) -> str:
        """Extract the assistant's text response from ACPX output.

        Handles plain text, JSON ACP messages, and NDJSON formats.
        """
        raw = raw_output.strip()
        if not raw:
            return ""

        # Strategy 1: Single JSON object
        try:
            data = json.loads(raw)
            return self._extract_from_acp_json(data)
        except json.JSONDecodeError:
            pass

        # Strategy 2: NDJSON
        lines = raw.split("\n")
        json_objects = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                json_objects.append(obj)
            except json.JSONDecodeError:
                continue

        if json_objects:
            for obj in reversed(json_objects):
                extracted = self._extract_from_acp_json(obj)
                if extracted:
                    return extracted

        # Strategy 3: Plain text (strip ANSI + wrapper lines)
        ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
        cleaned = ansi_escape.sub("", raw)

        result_lines = []
        skip_prefixes = (
            "Session:",
            "Connected to",
            "Using model:",
            "---",
            ">>>",
        )
        for line in cleaned.split("\n"):
            stripped = line.strip()
            if any(stripped.startswith(prefix) for prefix in skip_prefixes):
                continue
            result_lines.append(line)

        return "\n".join(result_lines).strip()

    def _extract_from_acp_json(self, data: Any) -> str:
        """Extract text content from a JSON ACP message object."""
        if isinstance(data, dict):
            if data.get("role") == "assistant":
                content = data.get("content", "")
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    texts = []
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            texts.append(block.get("text", ""))
                    return "\n".join(texts)

            if "response" in data:
                return str(data["response"])

            if "messages" in data and isinstance(data["messages"], list):
                for msg in reversed(data["messages"]):
                    if isinstance(msg, dict) and msg.get("role") == "assistant":
                        return str(msg.get("content", ""))

            if "content" in data:
                return str(data["content"])

            if "output" in data:
                return str(data["output"])

        if isinstance(data, str):
            return data

        return ""

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def reset_session(self, stage: int) -> None:
        """Reset/clear a session for a specific stage."""
        session_name = f"{self.session_prefix}-stage-{stage}"
        try:
            subprocess.run(
                ["acpx", "session", "delete", session_name],
                capture_output=True,
                text=True,
                timeout=10,
            )
            logger.info("Reset ACPX session: %s", session_name)
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            logger.warning("Failed to reset session %s: %s", session_name, exc)


class AcpxError(Exception):
    """Error from LLM CLI invocation (ACPX or Claude CLI)."""
    pass
