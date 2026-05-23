"""MCP Tool: get_answer - RAG-style synthesis over the wiki layer.

Single-call retrieval + LLM synthesis. Replaces the agent's multi-turn
search -> context -> read loop with one tool call that returns:

    {
      "answer":            str   - 2â€"5 sentence synthesised answer
      "citations":         list  - file paths backing the answer
      "confidence":        str   - "high" | "medium" | "low"
      "fallback_targets":  list  - top retrieval hits the agent should Read
                                   to verify (always present)
      "retrieval":         list  - raw top-N hits with snippets
    }

When no LLM provider is configured, the tool degrades to retrieval-only
mode (returns ranked hits + snippets, confidence="low") so C1 / index-only
deployments still benefit from the structured single-call shortcut.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json as _json
import os
import time
from pathlib import Path
from typing import Any

from sqlalchemy import select

from provenant.core.persistence.database import get_session
from provenant.core.persistence.models import AnswerCache, Page, WikiSymbol
from provenant.server.mcp_server._helpers import (
    _get_repo,
    _resolve_repo_context,
    _unsupported_repo_all,
)
from provenant.server.mcp_server._meta import answer_hint as _answer_hint
from provenant.server.mcp_server._meta import build_meta as _build_meta
from provenant.server.mcp_server._server import mcp

# How many top retrieval hits to enrich with WikiSymbol context. Enriching
# every hit produces large responses that bloat the cached prompt prefix on
# multi-turn agent sessions without changing the answer - the agent typically
# cites the top-1 file. Top-2 captures the primary navigation need with a
# bounded payload.
_ENRICH_TOP_N_HITS = 2
# How many symbols per enriched file. Bounded to keep the context block from
# growing unboundedly on dense files. We allocate more slots to the top hit
# (where the answer usually lives) and fewer to secondary hits.
_MAX_SYMBOLS_TOP_HIT = 10
_MAX_SYMBOLS_PER_HIT = 4

# When a retrieved file contains symbols whose name matches an identifier
# from the question, we promote those to the top of the symbol list for that
# file, pass a longer docstring, and attach a source excerpt so the LLM
# actually sees the method body - not just a stub docstring. Without this,
# specific-method questions get hedged answers even on dominant retrievals.
_MATCHED_SYMBOL_DOC_CHARS = 400
_MATCHED_SYMBOL_SOURCE_LINES = 40

# Sort priority by symbol kind. Classes first because "what does X do" /
# "which class inherits from Y" questions resolve at the class level. Then
# top-level functions, then methods (which usually only matter once the
# class context is established).
_KIND_PRIORITY = {"class": 0, "interface": 0, "function": 1, "method": 2}
# Per-symbol docstring truncation. Keeps the context block bounded - the
# first sentence is typically sufficient and trailing prose mostly contributes
# cache-write cost on follow-up turns.
_MAX_SYMBOL_DOC_CHARS = 120

# Confidence gate for synthesis. When the top retrieval hit is NOT clearly
# dominant relative to the second-best hit, skip LLM synthesis and return
# ranked snippets only. This forces the agent to ground in source rather than
# trust a possibly-wrong frame. Generic, repo-agnostic, no question parsing.
# Failure modes addressed:
#   (a) wrong-target retrieval where top-1 and top-2 are both plausible;
#   (b) synthesis hallucination on tangential top hits.
_DOMINANCE_RATIO = 1.2
_COVERAGE_THRESHOLD = 0.66

# Hedge-phrase markers that indicate the LLM refused to synthesize even though
# retrieval was dominant. When the answer contains any of these, we downgrade
# confidence to "low" and drop the retrieval payload - the hits aren't useful
# to a consumer that has already been told to go read the source, and letting
# them ride through the conversation cache inflates multi-turn cost.
_HEDGE_MARKERS = (
    "do not contain",
    "does not contain",
    "is not contained",
    "are not contained",
    "not contain sufficient",
    "not contain enough",
    "is not covered",
    "not covered in the",
    "not covered by the",
    "you should inspect",
    "you should consult",
    "consult the source",
    "inspect the source",
    "cannot be determined",
    "cannot determine",
    "is not clear",
    "insufficient information",
    "not enough information",
    "without more context",
    "without additional context",
    "didn't surface",
    "did not surface",
    "was not surfaced",
    "was not found in",
)


def _extract_question_identifiers(question: str) -> set[str]:
    """Pull out Python-looking identifiers the question names explicitly.

    Targets: snake_case (``_local_reachability_density``), CamelCase
    (``NearestCentroid``), dotted paths (``BaseLabelPropagation.fit``).
    Filtered to â‰¥3 chars, non-stopwords, non-pure-lowercase-English (unless
    they contain an underscore or a digit - otherwise every common word
    matches). The result drives question-aware symbol promotion in
    ``_hydrate_symbols_for_hits``.
    """
    import re

    ids: set[str] = set()
    # Match bare identifiers and dotted paths: first char letter/underscore,
    # rest alnum/underscore, optionally with dotted continuations.
    for tok in re.findall(r"[A-Za-z_][A-Za-z0-9_]*(~=:\.[A-Za-z_][A-Za-z0-9_]*)*", question):
        # Split dotted paths into both the full thing and the leaf.
        parts = tok.split(".")
        candidates = [tok] + parts
        for c in candidates:
            if len(c) < 3:
                continue
            if c.lower() in _STOPWORDS:
                continue
            # Heuristic: keep if it contains an uppercase letter anywhere
            # (covers CamelCase and sentence-initial capitalised nouns like
            # ``Version`` that are typically class names in Python), a
            # digit, or an underscore. Pure-lowercase English words like
            # ``method`` / ``class`` / ``dtype`` are dropped - they are
            # poor promotion signals and match too broadly.
            has_upper = any(ch.isupper() for ch in c)
            has_under = "_" in c
            has_digit = any(ch.isdigit() for ch in c)
            if has_upper or has_under or has_digit:
                ids.add(c)
    return ids


def _read_symbol_source(
    repo_root: Path | None,
    file_path: str,
    start_line: int,
    end_line: int,
    max_lines: int = _MATCHED_SYMBOL_SOURCE_LINES,
) -> str | None:
    """Return the literal source body for a symbol, bounded to max_lines.

    The bounded source is the key ingredient for question-matched symbols.
    The LLM was already getting the file-level summary and a truncated
    docstring; what it was missing was the actual code. With 40 lines of
    the method body in front of it, the synthesis step can answer "how
    does X work" without hedging back to "you should inspect the source".
    """
    if repo_root is None or start_line < 1:
        return None
    try:
        abs_path = (repo_root / file_path).resolve()
        try:
            abs_path.relative_to(repo_root.resolve())
        except ValueError:
            return None
        text = abs_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    lines = text.splitlines()
    if start_line > len(lines):
        return None
    hi = end_line if end_line and end_line >= start_line else start_line + max_lines
    hi = min(hi, start_line + max_lines, len(lines))
    body = "\n".join(lines[start_line - 1:hi])
    return body


def _answer_is_hedged(answer_text: str) -> bool:
    """True when the synthesized answer confesses it can't answer.

    Retrieval dominance alone doesn't tell you whether the LLM produced a
    usable answer - the underlying model happily admits insufficiency even
    on a top-scoring hit. Treat an admitted non-answer as low confidence,
    regardless of how dominant retrieval was.
    """
    low = (answer_text or "").lower()
    return any(marker in low for marker in _HEDGE_MARKERS)

# The dominance ratio threshold (top_score / second_score >= 1.2x) separates
# reliable retrievals from ambiguous ones. This is a property of BM25-style
# retrieval with a coverage re-ranker on top, not of any particular repository;
# tune if a deployment shows systematic over- or under-gating.

# When the gate triggers and we drop synthesis, fetch this many chars of
# real page content per top hit so the agent has substantive raw material
# to ground in (vs. one-line summary that's too thin to act on).
_GATED_EXCERPT_CHARS = 600
_GATED_RETURN_HITS = 3

# Intersection-retrieval connectives. If a question contains any of these
# (case-insensitive whole-word), it's likely a relational/multi-entity
# question. We split the question on the connective, run two FTS passes,
# and boost any page that appears in BOTH result sets - the page at the
# intersection is much more likely to be the actual answer than a page
# at the top of either single-side query.
# This is grammar, not domain - the same list applies to any English-language
# code question, independent of the repository or codebase.
_RELATIONAL_CONNECTIVES = (
    " between ", " from ", " across ", " through ", " with ",
    " and ", " versus ", " vs ",
)

# Term-coverage re-ranker tuning. Multiplies BM25 by (FLOOR + (1-FLOOR)*coverage)
# where coverage = (# distinct query terms present in hit) / (# query terms).
# FLOOR=0.5 -> single-concept questions (coverageâ‰ˆ1.0) are unaffected;
# multi-constraint questions where a hit covers 1/3 of terms get scored at 0.67
# of their raw BM25 (vs 1.0 for a hit covering 3/3). Conjunctive coverage
# becomes a tie-breaker rather than a hard filter.
_COVERAGE_FLOOR = 0.5
# English stopwords - minimal list, just enough to keep "what is the" from
# dominating coverage. Not language-specific, not repo-specific.
_STOPWORDS = frozenset({
    "a","an","the","is","are","was","were","be","been","being","of","to","in",
    "on","at","by","for","with","from","as","that","this","these","those","it",
    "its","and","or","but","not","no","do","does","did","done","have","has",
    "had","what","which","who","whom","whose","when","where","why","how","can",
    "could","should","would","may","might","will","shall","i","you","he","she",
    "we","they","me","him","her","us","them","my","your","his","their","our",
    "if","then","than","so","such","there","here","about","into","through",
    "between","across","over","under","up","down","out","off","via",
})
# Cap on bytes read from source per symbol when we recover a real signature
# from disk (multi-line def with type annotations). Anything longer than this
# gets truncated; the agent can call get_symbol for the full body.
_MAX_RICH_SIG_LINES = 4


def _hash_question(question: str) -> str:
    """Stable SHA-256 of the normalized question. Lowercase + strip + collapse ws."""
    norm = " ".join(question.lower().strip().split())
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def _compute_attribution_confidence(citations: list[str], fallback_targets: list[str]) -> float:
    """Citation density: fraction of retrieved pages actually cited in the answer.

    High density (≥0.6) → synthesis is grounded in retrieved pages.
    Low density (<0.3)  → LLM filled gaps from weights; answer may hallucinate.

    This is a zero-cost post-synthesis quality signal — no extra LLM call.
    """
    if not fallback_targets:
        return 0.0
    cited_set = {Path(c).as_posix().lower() for c in citations}
    retrieved_set = {Path(t).as_posix().lower() for t in fallback_targets}
    overlap = cited_set & retrieved_set
    return len(overlap) / len(retrieved_set)


def _log_confidence(
    repo_path: str | None,
    question: str,
    confidence_score: float,
    citations: list[str],
    fallback_targets: list[str],
    confidence_label: str,
) -> None:
    """Append a confidence record to .provenant/confidence_log.jsonl.

    Low-confidence records (score < 0.4) are the training signal for
    provenant improve — they identify wiki pages that were retrieved but
    failed to ground the answer, i.e., candidates for re-generation.
    """
    if not repo_path:
        return
    log_path = Path(repo_path) / ".provenant" / "confidence_log.jsonl"
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        import json as _json2
        record = {
            "ts": time.time(),
            "question": question[:300],
            "confidence_score": round(confidence_score, 3),
            "confidence_label": confidence_label,
            "citations": citations,
            "retrieved": fallback_targets,
            "uncited": [t for t in fallback_targets
                        if Path(t).as_posix().lower() not in
                        {Path(c).as_posix().lower() for c in citations}],
        }
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(_json2.dumps(record) + "\n")
    except Exception:
        pass  # logging must never break the response


# ── Low-confidence background repair ─────────────────────────────────────────

_AUTO_REPAIR_THRESHOLD = 0.35   # confidence below this triggers background repair
_AUTO_REPAIR_COOLDOWN  = 300    # seconds — don't re-repair the same page within 5 min
_auto_repair_last: dict[str, float] = {}  # page_path -> last repair timestamp


async def _background_repair(
    repo_path: str,
    uncited_pages: list[str],
    session_factory: Any,
    provider: Any,
) -> None:
    """Rewrite wiki pages that were retrieved but never cited — zero user latency.

    Fires as a fire-and-forget asyncio.Task immediately after a low-confidence
    response is returned to the caller.  The caller is not blocked.

    Only repairs pages that haven't been touched in the last _AUTO_REPAIR_COOLDOWN
    seconds to avoid hammering the LLM on repeated low-confidence queries.
    """
    import structlog as _sl
    log = _sl.get_logger(__name__)

    now = time.monotonic()
    to_repair = [
        p for p in uncited_pages
        if (now - _auto_repair_last.get(p, 0)) > _AUTO_REPAIR_COOLDOWN
    ]
    if not to_repair:
        return

    _SYSTEM = (
        "You are Provenant, a codebase intelligence engine. "
        "Rewrite the given wiki page so it is more precise and retrieval-specific. "
        "The page was retrieved for a relevant query but the synthesized answer never "
        "cited it — the page is too generic or misses the key concepts. "
        "Focus on: (1) the file's exact architectural role, (2) specific public APIs "
        "with their signatures, (3) concrete problems this file solves. "
        "Use precise names from the source. No preamble. Return ONLY the improved markdown."
    )

    from sqlalchemy import select

    from provenant.core.persistence.models import Page

    # session_factory is already an async_sessionmaker — use it directly.
    factory = session_factory

    for page_path in to_repair:
        try:
            # Load existing DB record
            async with factory() as session:
                result = await session.execute(
                    select(Page).where(Page.target_path == page_path)
                )
                existing = result.scalars().first()
                if not existing:
                    result = await session.execute(
                        select(Page).where(
                            Page.target_path.ilike(f"%{Path(page_path).name}%")
                        )
                    )
                    existing = result.scalars().first()

            if not existing:
                continue

            # Read source file
            abs_path = Path(repo_path) / page_path
            if not abs_path.exists():
                candidates = list(Path(repo_path).rglob(Path(page_path).name))
                abs_path = candidates[0] if candidates else None
            if not abs_path or not abs_path.exists():
                continue

            source_text = abs_path.read_text(encoding="utf-8", errors="replace")

            user_prompt = (
                f"## Attribution feedback\n"
                f"File: `{page_path}`\n"
                f"This page was retrieved for a query but never cited in the answer. "
                f"The current summary is too generic — rewrite it so it only surfaces "
                f"for queries where this file is actually relevant.\n\n"
                f"## Current wiki page\n"
                f"{existing.content or '(no content)'}\n\n"
                f"## Source file (first 4000 chars)\n"
                f"```\n{source_text[:4000]}\n```\n\n"
                f"Return ONLY the improved markdown wiki page."
            )

            response = await asyncio.wait_for(
                provider.generate(
                    system_prompt=_SYSTEM,
                    user_prompt=user_prompt,
                    max_tokens=1500,
                    temperature=0.2,
                ),
                timeout=45.0,
            )
            new_content = (response.content or "").strip()
            if not new_content:
                continue

            first_line = next(
                (ln.lstrip("# ").strip() for ln in new_content.splitlines() if ln.strip()),
                existing.summary or page_path,
            )

            async with factory() as session:
                existing_db = await session.get(Page, existing.id)
                if existing_db:
                    existing_db.content = new_content
                    existing_db.summary = first_line[:200]
                    await session.commit()

            _auto_repair_last[page_path] = now
            log.debug("auto_repair.done", page=page_path)

        except asyncio.TimeoutError:
            log.debug("auto_repair.timeout", page=page_path)
        except Exception as exc:
            log.debug("auto_repair.error", page=page_path, error=str(exc))


async def _generate_hypothetical_doc(question: str, provider: Any) -> str | None:
    """HyDE: generate a short hypothetical wiki snippet for the question.

    The snippet uses the same vocabulary as real wiki pages, so retrieving
    against it (rather than the raw question) closes the vocabulary gap between
    natural-language questions and technical documentation.

    Returns None silently on timeout or any error — callers fall back to BM25.
    """
    _hyde_system = (
        "You are indexing a Python codebase wiki. "
        "Write ONE 2-sentence snippet (file path + what it does) that would "
        "directly answer the developer question below. "
        "Be specific: include likely class names, method names, and file paths. "
        "Output only the snippet, nothing else."
    )
    _hyde_user = f"Question: {question}"
    try:
        response = await asyncio.wait_for(
            provider.generate(
                system_prompt=_hyde_system,
                user_prompt=_hyde_user,
                max_tokens=120,
                temperature=0.0,
            ),
            timeout=8.0,
        )
        text = (response.content or "").strip()
        return text if text else None
    except Exception:
        return None


_log = __import__("logging").getLogger("provenant.mcp.answer")

_SYSTEM_PROMPT = (
    "You are a codebase Q&A assistant with access to pre-filtered, high-signal wiki excerpts. "
    "The context you receive has already been scored and compressed — low-relevance pages "
    "were removed before reaching you. Trust the context: if a symbol's source body or "
    "signature is present, you have enough material to answer directly without hedging. "
    "Answer concretely. Cite source files by relative path inline like `path/to/file.py` "
    "and include line numbers when available. "
    "For mechanism or architecture questions: use headings, bullets, and a short code block "
    "from the actual source body — not a paragraph. "
    "For lookup questions (what does X do, what are the params): answer in 2-4 sentences. "
    "Aim for 100-350 words — cover the question completely without padding. "
    "Only hedge ('the excerpts do not contain...') when there is genuinely no relevant "
    "signature, docstring, or source body in the provided context. "
    "Never invent file paths or function signatures."
)

_USER_TEMPLATE = """\
Question: {question}

Codebase wiki excerpts ({n} pages, pre-filtered for relevance):

{context}

Answer the question directly. Cite file paths inline and line numbers when provided.
Use a structured layout (headings, bullets, code block) for mechanism or architecture questions.
For simple lookups, 2-4 sentences is sufficient.
"""


def _load_repo_provider_config(
    repo_path: Path | None,
) -> tuple[str | None, str | None, dict[str, str]]:
    """Read persisted provider config for a repo.

    `provenant init` writes the chosen provider + model into
    ``.provenant/state.json`` and the corresponding API key into
    ``.provenant/.env``. The MCP server doesn't load that .env at startup,
    so without this helper get_answer can't reach an LLM unless the user
    also exports PROVENANT_PROVIDER / OPENAI_API_KEY in the shell that
    launched Claude Code. This recovers the persisted values so the same
    provider used for init / update is reused for get_answer.

    Returns ``(provider_name, model, env_overlay)``. Any field may be
    None / empty - callers should fall back to process env when missing.
    """
    if repo_path is None:
        return None, None, {}

    state_path = repo_path / ".provenant" / "state.json"
    env_path = repo_path / ".provenant" / ".env"

    name: str | None = None
    model: str | None = None
    overlay: dict[str, str] = {}

    try:
        if state_path.is_file():
            data = _json.loads(state_path.read_text(encoding="utf-8"))
            name = data.get("provider") or None
            model = data.get("model") or None
    except Exception:
        _log.debug("Failed to read %s", state_path, exc_info=True)

    try:
        if env_path.is_file():
            for raw_line in env_path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip("'").strip('"')
                if key:
                    overlay[key] = val
    except Exception:
        _log.debug("Failed to read %s", env_path, exc_info=True)

    return name, model, overlay


def _resolve_provider_for_answer(repo_path: Path | None = None):
    """Best-effort provider lookup mirroring cli/helpers.resolve_provider.

    Avoids the click dependency from the cli package. Returns a BaseProvider
    or None if no API key / provider is configured.

    Resolution order: process env vars first, then ``.provenant/state.json``
    + ``.provenant/.env`` for the active repo. The persisted values are the
    same ones ``provenant init`` and ``provenant update`` use, so get_answer
    follows the user's existing provider choice without a separate config.
    """
    try:
        from provenant.llm.providers.llm.registry import get_provider
    except Exception:
        _log.warning("Provider registry import failed", exc_info=True)
        return None

    persisted_name, persisted_model, env_overlay = _load_repo_provider_config(
        repo_path
    )

    def _env(key: str) -> str | None:
        # Prefer real process env so an explicit shell export still wins;
        # fall back to .provenant/.env only when the process env is empty.
        return os.environ.get(key) or env_overlay.get(key) or None

    name = os.environ.get("PROVENANT_PROVIDER") or persisted_name
    model = (
        os.environ.get("PROVENANT_DOC_MODEL")
        or os.environ.get("PROVENANT_MODEL")
        or persisted_model
    )

    def _try(provider_name: str, **kwargs: Any):
        try:
            return get_provider(provider_name, **kwargs)
        except Exception:
            _log.warning("get_provider(%s) failed", provider_name, exc_info=True)
            return None

    def _resolve_base_url(provider_name: str) -> str | None:
        mapping = {
            "openai": ["OPENAI_BASE_URL"],
            "anthropic": ["ANTHROPIC_BASE_URL"],
            "gemini": ["GEMINI_BASE_URL"],
            "deepseek": ["DEEPSEEK_BASE_URL"],
            "ollama": ["OLLAMA_BASE_URL"],
            "litellm": ["LITELLM_BASE_URL", "LITELLM_API_BASE"],
        }
        for env_var in mapping.get(provider_name, []):
            val = _env(env_var)
            if val:
                return val
        return None

    # Explicit selection wins.
    if name:
        kw: dict[str, Any] = {}
        if model:
            kw["model"] = model
        if name == "anthropic" and _env("ANTHROPIC_API_KEY"):
            kw["api_key"] = _env("ANTHROPIC_API_KEY")
        elif name == "openai" and _env("OPENAI_API_KEY"):
            kw["api_key"] = _env("OPENAI_API_KEY")
        elif name == "deepseek" and _env("DEEPSEEK_API_KEY"):
            kw["api_key"] = _env("DEEPSEEK_API_KEY")
        elif name == "gemini" and (
            _env("GEMINI_API_KEY") or _env("GOOGLE_API_KEY")
        ):
            kw["api_key"] = _env("GEMINI_API_KEY") or _env("GOOGLE_API_KEY")
        base_url = _resolve_base_url(name)
        if base_url:
            kw["base_url"] = base_url
        return _try(name, **kw)

    # Auto-detect from API keys.
    if _env("ANTHROPIC_API_KEY"):
        kw = {"api_key": _env("ANTHROPIC_API_KEY")}
        if model:
            kw["model"] = model
        base_url = _resolve_base_url("anthropic")
        if base_url:
            kw["base_url"] = base_url
        return _try("anthropic", **kw)
    if _env("OPENAI_API_KEY"):
        kw = {"api_key": _env("OPENAI_API_KEY")}
        if model:
            kw["model"] = model
        base_url = _resolve_base_url("openai")
        if base_url:
            kw["base_url"] = base_url
        return _try("openai", **kw)
    if _env("GEMINI_API_KEY") or _env("GOOGLE_API_KEY"):
        kw = {"api_key": _env("GEMINI_API_KEY") or _env("GOOGLE_API_KEY")}
        if model:
            kw["model"] = model
        base_url = _resolve_base_url("gemini")
        if base_url:
            kw["base_url"] = base_url
        return _try("gemini", **kw)
    if _env("OLLAMA_BASE_URL"):
        kw = {"base_url": _env("OLLAMA_BASE_URL")}
        if model:
            kw["model"] = model
        return _try("ollama", **kw)
    if _env("DEEPSEEK_API_KEY"):
        kw = {"api_key": _env("DEEPSEEK_API_KEY")}
        if model:
            kw["model"] = model
        base_url = _resolve_base_url("deepseek")
        if base_url:
            kw["base_url"] = base_url
        return _try("deepseek", **kw)
    return None


def _query_focused_compress(text: str, question: str, max_chars: int) -> str:
    """Extractive sentence-level compression: keep only the sentences from
    ``text`` that are most relevant to ``question``, up to ``max_chars``.

    This is the correct granularity for compressing an already high-signal
    wiki page. Whole-page removal (BM25 ratio, MMR) causes information loss
    because each page covers unique aspects. Sentence-level extraction
    preserves page coverage while reducing tokens by ~40-60%.

    Scoring: token overlap between question terms and sentence terms
    (equivalent to unigram BM25 with no IDF). Fast O(n) string operation,
    no model loading needed.
    """
    import re
    if len(text) <= max_chars:
        return text

    # Sentence-split on ". " or ".\n" preserving boundaries
    raw = re.split(r"(?<=[.!?])\s+", text.strip())
    sentences = [s.strip() for s in raw if len(s.strip()) > 15]
    if not sentences:
        return text[:max_chars]

    q_tokens = set(re.findall(r"[a-z_][a-z0-9_]{2,}", question.lower()))
    q_tokens -= _STOPWORDS

    def _score(s: str) -> float:
        s_tokens = set(re.findall(r"[a-z_][a-z0-9_]{2,}", s.lower()))
        return len(q_tokens & s_tokens) / max(len(q_tokens), 1)

    # Rank sentences but preserve document order for the kept set
    ranked = sorted(range(len(sentences)), key=lambda i: _score(sentences[i]), reverse=True)
    kept_indices: set[int] = set()
    budget = max_chars
    for idx in ranked:
        sent_len = len(sentences[idx]) + 2  # +2 for ". "
        if budget <= 0:
            break
        kept_indices.add(idx)
        budget -= sent_len

    # Reconstruct in original document order
    result = " ".join(sentences[i] for i in sorted(kept_indices))
    return result[:max_chars]


def _build_context_block(
    hits: list[dict],
    max_chars_per_hit: int = 800,
    question: str = "",
    compress: bool = False,
) -> str:
    """Format retrieval hits as a compact text block for the LLM.

    Each hit includes:
      * file path + title + retrieval score
      * file-level summary (Page.summary, capped at max_chars_per_hit)
      * per-symbol signature + docstring; for question-matched symbols
        (flagged ``_matched`` by ``_hydrate_symbols_for_hits``) the
        docstring runs to 400 chars and we append up to 40 lines of the
        actual source body as a fenced code block. The source body is
        what lets the LLM answer "how does X work" instead of hedging.
    """
    parts = []
    for i, h in enumerate(hits, start=1):
        body_src = h.get("summary") or h.get("snippet") or ""
        body = body_src[:max_chars_per_hit]
        block = [
            f"[{i}] {h['target_path']} (score={h['score']:.3f})",
            f"    title: {h['title']}",
            f"    summary: {body}",
        ]
        symbols = h.get("symbols") or []
        if symbols:
            block.append("    symbols:")
            for s in symbols:
                sig = s.get("signature") or s.get("name") or ""
                kind = s.get("kind") or "~="
                matched = bool(s.get("_matched"))
                doc = (s.get("docstring") or "").strip()
                doc_cap = _MATCHED_SYMBOL_DOC_CHARS if matched else _MAX_SYMBOL_DOC_CHARS
                tag = " [question-match]" if matched else ""
                block.append(f"      - [{kind}]{tag} {sig}")
                if doc:
                    trimmed = " ".join(doc.split())[:doc_cap]
                    block.append(f"          docstring: {trimmed}")
                src = s.get("source_excerpt")
                if src:
                    block.append("          source:")
                    for line in src.splitlines():
                        block.append(f"              {line}")
        parts.append("\n".join(block))
    return "\n\n".join(parts)


def _read_signature_from_source(
    repo_root: Path | None, file_path: str, start_line: int
) -> str | None:
    """Read the symbol's actual signature line from disk.

    Returns the def/class line (or its multi-line continuation) verbatim from
    the source file. Captures everything WikiSymbol.signature strips:
      * base classes for `class Foo(Bar, Baz):`
      * decorators (one line above the def)
      * full type annotations across line continuations

    None on any failure - caller falls back to the stored signature.
    """
    if repo_root is None:
        return None
    try:
        abs_path = (repo_root / file_path).resolve()
        # Defense in depth: never read outside the repo root.
        try:
            abs_path.relative_to(repo_root.resolve())
        except ValueError:
            return None
        text = abs_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    lines = text.splitlines()
    if not lines or start_line < 1 or start_line > len(lines):
        return None
    # Walk forward up to _MAX_RICH_SIG_LINES until we close the parenthesis
    # group (Python signatures often span multiple lines for type hints).
    sig_lines: list[str] = []
    paren_depth = 0
    for i in range(start_line - 1, min(start_line - 1 + _MAX_RICH_SIG_LINES, len(lines))):
        line = lines[i]
        sig_lines.append(line.strip())
        paren_depth += line.count("(") - line.count(")")
        if line.rstrip().endswith(":") and paren_depth <= 0:
            break
    if not sig_lines:
        return None
    return " ".join(sig_lines)


async def _hydrate_symbols_for_hits(
    session,
    repo_id: str,
    hits: list[dict],
    ctx: Any = None,
    question_ids: set[str] | None = None,
) -> None:
    """Mutate `hits` in place: attach `symbols` list to top-N file_page hits.

    Question-aware promotion: if ``question_ids`` contains identifiers that
    match symbols in the retrieved files, those symbols move to the top of
    their file's symbol list, carry a longer docstring, and get a source
    excerpt (``source_excerpt``). This is the difference between the LLM
    seeing ``class LocalOutlierFactor`` at the file top (and hedging on a
    question about ``_local_reachability_density``) vs. seeing the actual
    method body and answering it.

    Top hit gets ``_MAX_SYMBOLS_TOP_HIT`` slots; secondaries get the smaller
    ``_MAX_SYMBOLS_PER_HIT``. Symbols not matching a question id carry the
    short 120-char docstring; matched symbols carry 400 chars + source body.
    """
    question_ids = question_ids or set()
    # Case-folded copy for matching.
    qids_lower = {q.lower() for q in question_ids}

    # Identify the top file_page hits in retrieval-rank order. `hits` is
    # already sorted by descending score upstream.
    enrich_paths: list[str] = []
    for h in hits:
        if (
            h.get("target_path")
            and h.get("page_type") == "file_page"
            and len(enrich_paths) < _ENRICH_TOP_N_HITS
        ):
            enrich_paths.append(h["target_path"])
    if not enrich_paths:
        return

    res = await session.execute(
        select(WikiSymbol)
        .where(
            WikiSymbol.repository_id == repo_id,
            WikiSymbol.file_path.in_(enrich_paths),
        )
        .order_by(WikiSymbol.file_path, WikiSymbol.start_line)
    )
    by_file: dict[str, list[dict]] = {}
    repo_root = Path(str(ctx.path)) if ctx and ctx.path else None
    for row in res.scalars().all():
        rich_sig = _read_signature_from_source(
            repo_root, row.file_path, row.start_line
        )
        # Does the symbol name match any identifier from the question~=
        name_lower = (row.name or "").lower()
        qname_lower = (row.qualified_name or "").lower()
        matched = bool(
            qids_lower
            and (
                name_lower in qids_lower
                or qname_lower in qids_lower
                or any(
                    q in name_lower or q in qname_lower
                    for q in qids_lower
                    if len(q) >= 5  # avoid spurious substring matches on short tokens
                )
            )
        )
        entry: dict[str, Any] = {
            "name": row.name,
            "kind": row.kind,
            "signature": rich_sig or row.signature,
            "docstring": row.docstring or "",
            "start_line": row.start_line,
            "end_line": row.end_line,
            "_matched": matched,
        }
        if matched:
            src = _read_symbol_source(
                repo_root, row.file_path, row.start_line, row.end_line
            )
            if src:
                entry["source_excerpt"] = src
        by_file.setdefault(row.file_path, []).append(entry)

    # Sort: matched symbols first (document order within the match group),
    # then unmatched in start_line order. Cap per file - top hit gets more
    # slots than secondary hits.
    for i, h in enumerate(hits):
        path = h.get("target_path")
        if path not in by_file:
            continue
        syms = by_file[path]
        syms.sort(key=lambda s: (not s["_matched"], s["start_line"]))
        cap = _MAX_SYMBOLS_TOP_HIT if i == 0 else _MAX_SYMBOLS_PER_HIT
        # Guarantee at least one matched symbol survives the cap, even if
        # the file has more than `cap` symbols before it.
        kept: list[dict] = [s for s in syms if s["_matched"]][: cap]
        for s in syms:
            if s in kept:
                continue
            if len(kept) >= cap:
                break
            kept.append(s)
        # Sort final slice by start_line for natural reading order.
        kept.sort(key=lambda s: s["start_line"])
        h["symbols"] = kept


def _split_relational(question: str) -> list[str] | None:
    """If the question is relational (contains a connective like 'and' or
    'between'), split it into two sub-queries on the FIRST matching
    connective. Returns [left, right] or None if not relational.

    Heuristic only - works on English grammar, not on code or repo terms.
    """
    q = " " + question.strip() + " "
    qlow = q.lower()
    for conn in _RELATIONAL_CONNECTIVES:
        idx = qlow.find(conn)
        if idx > 0:
            left = q[:idx].strip()
            right = q[idx + len(conn):].strip()
            # Both sides must have at least 3 content terms to be a real
            # multi-entity question (not e.g. "what is X and how").
            if len(_question_terms(left)) >= 3 and len(_question_terms(right)) >= 3:
                return [left, right]
    return None


async def _intersection_boost(question: str, hits: list[dict], ctx: Any = None) -> None:
    """For relational questions, boost any hit that appears in both halves
    of a split-FTS retrieval. Mutates `hits` in place: adds a multiplicative
    bonus to `score` for hits that appear in both subset retrievals.

    Universal IR principle: pages at the intersection of two query halves
    are much more likely to answer relational questions than pages at the
    top of either half alone. Independent of repo or domain.
    """
    parts = _split_relational(question)
    if parts is None or ctx is None or ctx.fts is None:
        return
    sub_hit_ids: list[set] = []
    for sub_q in parts:
        try:
            sub = await asyncio.wait_for(
                ctx.fts.search(sub_q, limit=15), timeout=3.0
            )
            sub_hit_ids.append({h.page_id for h in sub})
        except Exception:
            return
    if len(sub_hit_ids) < 2:
        return
    intersection = sub_hit_ids[0] & sub_hit_ids[1]
    if not intersection:
        return
    # 2Ã- boost for hits at the intersection - strong enough to overtake
    # a single-side top hit, not so strong that it ignores BM25 entirely.
    for h in hits:
        if h.get("page_id") in intersection:
            h["score"] = h.get("score", 0.0) * 2.0
            h["_intersection"] = True
    hits.sort(key=lambda h: h["score"], reverse=True)


async def _enrich_gated_excerpts(hits: list[dict], ctx: Any = None) -> None:
    """For the gated (low-confidence) return path, fetch real page content
    for top hits so the agent has substantive raw material instead of
    one-line summaries. Mutates `hits` in place - adds an `excerpt` field.

    Universal motivation: thin retrieval output forces consumers to fall
    back on priors instead of grounding in source. Symmetric with the
    enrichment we already do for synthesis.
    """
    if not hits:
        return
    page_ids = [h["page_id"] for h in hits[:_GATED_RETURN_HITS] if h.get("page_id")]
    if not page_ids:
        return
    try:
        async with get_session(ctx.session_factory) as session:
            res = await session.execute(
                select(Page.id, Page.content_md).where(Page.id.in_(page_ids))
            )
            content_by_id = {row[0]: (row[1] or "") for row in res.all()}
    except Exception:
        return
    for h in hits[:_GATED_RETURN_HITS]:
        body = content_by_id.get(h.get("page_id"), "")
        if body:
            h["excerpt"] = body[:_GATED_EXCERPT_CHARS]


def _question_terms(question: str) -> list[str]:
    """Extract content terms from a question. Lowercase, alnum-tokenized,
    stopwords + length<3 dropped. Used by the term-coverage re-ranker."""
    import re
    raw = re.findall(r"[a-zA-Z0-9_]+", question.lower())
    return [t for t in raw if len(t) >= 3 and t not in _STOPWORDS]


def _rerank_by_coverage(hits: list[dict], question: str) -> list[dict]:
    """Re-rank FTS hits by term-coverage boost on top of BM25.

    For each hit, compute the fraction of distinct query terms present in
    (title + snippet + summary), then multiply the raw BM25 score by
    (FLOOR + (1-FLOOR)*coverage). Single-concept questions (coverageâ‰ˆ1.0
    across all hits) are unaffected; multi-constraint questions push hits
    that cover all the terms above hits that repeat just one term.

    This addresses a common BM25 failure mode where a hit that matches one
    constraint very strongly can outrank a hit that matches all constraints
    moderately - the latter is usually the better answer for multi-constraint
    questions.
    """
    terms = set(_question_terms(question))
    if not terms or not hits:
        return hits
    n_terms = len(terms)
    for h in hits:
        haystack = " ".join([
            h.get("title", "") or "",
            h.get("snippet", "") or "",
            h.get("summary", "") or "",
        ]).lower()
        # Count distinct terms present (substring match - FTS5 already handles
        # stemming upstream, so we keep this simple).
        present = sum(1 for t in terms if t in haystack)
        coverage = present / n_terms
        raw = h.get("score", 0.0)
        h["_coverage"] = coverage
        h["_raw_score"] = raw
        h["score"] = raw * (_COVERAGE_FLOOR + (1.0 - _COVERAGE_FLOOR) * coverage)
    hits.sort(key=lambda h: h["score"], reverse=True)
    return hits


async def _safe_fts_search(fts: Any, query: str, limit: int = 15) -> list:
    """BM25 search, returning [] on timeout or any error."""
    with contextlib.suppress(Exception):
        return await asyncio.wait_for(fts.search(query, limit=limit), timeout=5.0)
    return []


async def _safe_vector_search(vector_store: Any, query: str, limit: int = 15) -> list:
    """Semantic vector search, returning [] on timeout or any error."""
    with contextlib.suppress(Exception):
        return await asyncio.wait_for(
            vector_store.search(query, limit=limit), timeout=8.0
        )
    return []


def _rrf_merge(fts_hits: list, vec_hits: list, k: int = 60, top_n: int = 8) -> list:
    """Reciprocal Rank Fusion of FTS and vector search results.

    score(doc) = Σ 1/(k + rank_in_list)  for each list the doc appears in.
    When the same page_id appears in both lists, its scores are summed —
    boosting docs that both engines agree on. The FTS SearchResult is kept
    as the canonical object (richer snippets) when there is overlap.
    """
    scores: dict[str, float] = {}
    canonical: dict[str, Any] = {}

    for rank, hit in enumerate(fts_hits):
        pid = hit.page_id
        scores[pid] = scores.get(pid, 0.0) + 1.0 / (k + rank)
        canonical.setdefault(pid, hit)

    for rank, hit in enumerate(vec_hits):
        pid = hit.page_id
        scores[pid] = scores.get(pid, 0.0) + 1.0 / (k + rank)
        canonical.setdefault(pid, hit)  # FTS canonical takes priority via setdefault

    ranked = sorted(scores.keys(), key=lambda pid: scores[pid], reverse=True)
    return [canonical[pid] for pid in ranked[:top_n]]


@mcp.tool()
async def provenant_ask(
    question: str,
    scope: str | None = None,
    repo: str | None = None,
    compress: bool = True,
    force_synthesize: bool = False,
    hyde: bool = True,
) -> dict:
    """One-call RAG: answer a code question. Always your first call.

    Returns {answer, citations, confidence, fallback_targets}. High-confidence
    answers name concrete files/symbols and can be used with less verification.
    For medium/low confidence, cross-reference with search_codebase + get_context.
    Always verify cited file paths exist before acting on them.

    Args:
        question: developer question.
        scope: optional path prefix to restrict retrieval (e.g. "src/pkg/").
        repo: repository identifier; usually omitted.
        compress: if False, skip Provenant's compression pruning (benchmark baseline mode).
        force_synthesize: if True, bypass the dominance gate and always call the LLM.
        hyde: if True (default), generate a hypothetical wiki snippet and merge vector
            search results with BM25 via RRF when the vector store is ready. Falls back
            silently to BM25-only when the vector store is not ready or provider unavailable.
    """
    if repo == "all":
        return _unsupported_repo_all("provenant_ask")

    t0 = time.perf_counter()
    ctx = await _resolve_repo_context(repo)

    if not question or not question.strip():
        return {
            "answer": "",
            "citations": [],
            "confidence": "low",
            "fallback_targets": [],
            "retrieval": [],
            "error": "question is required",
            "_meta": _build_meta(timing_ms=(time.perf_counter() - t0) * 1000),
        }

    async with get_session(ctx.session_factory) as session:
        repository = await _get_repo(session)
        repo_id = repository.id

    # --- Cache lookup --------------------------------------------------------
    # Scope: ignore the (rare) `scope` argument in the cache key for now;
    # scoped queries are uncommon and including scope would balloon hit rate
    # variance. We hash on (repo_id, normalized_question) only.
    qhash = _hash_question(question)
    async with get_session(ctx.session_factory) as session:
        res = await session.execute(
            select(AnswerCache).where(
                AnswerCache.repository_id == repo_id,
                AnswerCache.question_hash == qhash,
            )
        )
        cached = res.scalar_one_or_none()
    if cached is not None and not force_synthesize:
        with contextlib.suppress(Exception):
            payload = _json.loads(cached.payload_json)
            # Bypass-on-hedged: if the cached answer hedged, the retrieval +
            # symbol pipeline has since been upgraded (question-aware symbol
            # promotion, source-body excerpts). Give synthesis another shot
            # with the new context rather than pinning the bad answer.
            if _answer_is_hedged(payload.get("answer", "")):
                _log.info("Bypassing hedged cache entry for re-synthesis")
            else:
                payload["_meta"] = _build_meta(
                    timing_ms=(time.perf_counter() - t0) * 1000,
                    cached=True,
                    hint=_answer_hint(
                        payload.get("confidence", "low"),
                        len(payload.get("retrieval", [])),
                    ),
                )
                return payload

    # --- Retrieval (FTS + optional HyDE vector search) ----------------------
    _hyde_used = False
    raw_hits: list[Any] = []

    # HyDE is viable when: vector store is ready AND backed by a real embedder
    # (not InMemoryVectorStore which uses MockEmbedder — random vectors are worse
    # than useless for retrieval) AND a provider is reachable.
    # We resolve the provider early here (cheap: reads env/config) so we can
    # reuse it later for synthesis — avoiding a second resolve call.
    _provider_early = None
    _vector_store_is_real = False
    if ctx.vector_store is not None and ctx.vector_store_ready is not None and ctx.vector_store_ready.is_set():
        from provenant.core.persistence.vector_store import InMemoryVectorStore as _InMemVS
        _vector_store_is_real = not isinstance(ctx.vector_store, _InMemVS)
    _hyde_viable = (
        hyde
        and ctx.fts is not None
        and _vector_store_is_real
    )
    if _hyde_viable:
        _provider_early = _resolve_provider_for_answer(getattr(ctx, "path", None))
        _hyde_viable = _provider_early is not None

    if _hyde_viable:
        # Parallel: generate hypothetical doc + run BM25 simultaneously.
        hyp_doc, fts_results = await asyncio.gather(
            _generate_hypothetical_doc(question, _provider_early),
            _safe_fts_search(ctx.fts, question, limit=15),
        )
        if hyp_doc:
            vec_results = await _safe_vector_search(ctx.vector_store, hyp_doc, limit=15)
            if vec_results:
                raw_hits = _rrf_merge(fts_results, vec_results, k=60, top_n=8)
                _hyde_used = True
            else:
                raw_hits = fts_results  # vector store empty — use full FTS list
        else:
            # Hypothetical doc generation failed — fall back to BM25 only.
            raw_hits = fts_results
    elif ctx.fts is not None:
        # BM25-only path (original behaviour, unchanged).
        raw_hits = await _safe_fts_search(ctx.fts, question, limit=15)

    # Hydrate hits with target_path + summary from the Page table.
    hits: list[dict] = []
    if raw_hits:
        page_ids = [h.page_id for h in raw_hits]
        async with get_session(ctx.session_factory) as session:
            res = await session.execute(
                select(
                    Page.id,
                    Page.target_path,
                    Page.summary,
                    Page.page_type,
                ).where(Page.id.in_(page_ids))
            )
            meta_by_id = {
                row[0]: {
                    "target_path": row[1],
                    "summary": row[2] or "",
                    "page_type": row[3],
                }
                for row in res.all()
            }
        for h in raw_hits:
            meta = meta_by_id.get(h.page_id, {})
            target_path = meta.get("target_path", "")
            if scope and target_path and not target_path.startswith(scope):
                continue
            hits.append(
                {
                    "page_id": h.page_id,
                    "title": h.title,
                    "target_path": target_path,
                    "page_type": meta.get("page_type", h.page_type),
                    "snippet": h.snippet,
                    "summary": meta.get("summary", ""),
                    "score": float(h.score or 0.0),
                }
            )

    # Term-coverage re-rank before the cap so conjunctive matches survive.
    hits = _rerank_by_coverage(hits, question)
    # Intersection-retrieval boost for relational questions (multi-entity).
    # Pages at the intersection of two split-FTS halves get a 2Ã- bonus.
    with contextlib.suppress(Exception):
        await _intersection_boost(question, hits, ctx)
    # Always cap retrieval hits at 5 for the response payload.
    hits = hits[:5]

    # Enrich each file_page hit with its top-N WikiSymbol rows. Question-
    # aware: identifiers extracted from the question promote matching
    # symbols and attach a source-body excerpt - the difference between a
    # hedged answer on a specific-method question and a grounded one.
    question_ids = _extract_question_identifiers(question)
    if hits:
        with contextlib.suppress(Exception):
            async with get_session(ctx.session_factory) as session:
                await _hydrate_symbols_for_hits(
                    session, repo_id, hits, ctx, question_ids=question_ids
                )

    fallback_targets = [
        h["target_path"] for h in hits if h.get("target_path")
    ]

    if not hits:
        return {
            "answer": "",
            "citations": [],
            "confidence": "low",
            "fallback_targets": [],
            "retrieval": [],
            "note": (
                "No wiki hits for this question. Fall back to "
                "search_codebase or Grep to locate candidate files."
            ),
            "_meta": _build_meta(
                timing_ms=(time.perf_counter() - t0) * 1000,
                hint=_answer_hint("low", 0),
            ),
        }

    # --- Provenant compression: prune low-signal pages before LLM call ---
    from provenant.core.compression.attribute import score_pages
    from provenant.core.compression.evaluate import format_compression_stats
    from provenant.core.compression.prune import prune_pages  # used post-synthesis

    _pages_for_scoring = [
        {
            "path": h.get("target_path", ""),
            "title": h.get("title", ""),
            "content": h.get("summary", "")
            + " "
            + " ".join(s.get("name", "") for s in h.get("symbols", [])),
            "symbols": [s.get("name", "") for s in h.get("symbols", [])],
        }
        for h in hits
    ]

    if compress:
        from provenant.core.compression.models import CompressionResult, PageScore as _PageScore
        _n_initial = len(hits)
        _initial_chars_pre = sum(len(p.get("content", "")) for p in _pages_for_scoring)
        _MAX_CHARS_PER_HIT = 800
        _final_chars_pre = sum(
            min(len(p.get("content", "")), _MAX_CHARS_PER_HIT) for p in _pages_for_scoring
        )
        _pre_compression = CompressionResult(
            kept_pages=_pages_for_scoring,
            pruned_pages=[],
            initial_count=_n_initial,
            final_count=_n_initial,
            initial_chars=_initial_chars_pre,
            final_chars=_final_chars_pre,
            compression_ratio=(_initial_chars_pre - _final_chars_pre) / max(_initial_chars_pre, 1),
            misleading_paths=[],
        )
        _compression_stats = format_compression_stats(_pre_compression)
    else:
        # Baseline mode: no pruning, return zero-compression stats for fair token logging
        _compression_stats = {
            "compression": {
                "initial_files": len(_pages_for_scoring),
                "final_files": len(_pages_for_scoring),
                "files_pruned": 0,
                "initial_chars": sum(len(p.get("content", "")) for p in _pages_for_scoring),
                "final_chars": sum(len(p.get("content", "")) for p in _pages_for_scoring),
                "compression_ratio": 0.0,
                "compression_pct": 0.0,
                "pruned_files": [],
            }
        }

    fallback_targets = [
        h["target_path"] for h in hits if h.get("target_path")
    ]
    # --- end Provenant compression ---

    # --- Confidence gate ---------------------------------------------------
    # Skip synthesis when retrieval is NOT clearly dominant. The dominance
    # ratio (top score / second score) is the sole gating criterion: above
    # the threshold the top hit is reliably the right answer; below it the
    # top-1 / top-2 ambiguity is large enough that we hand the agent ranked
    # excerpts and let it ground in source.
    #
    # Coverage (fraction of query terms present in the top hit) is also
    # available via the re-ranker and is used to bias score-based ranking,
    # but is intentionally NOT used as a hard gate here. Natural-language
    # questions rarely have all their content terms co-occurring in a single
    # page (typical coverage is 0.15â€"0.25), so a coverage threshold over-
    # fires on confidently-dominant retrievals and degrades the cheap path.
    if len(hits) >= 2:
        top_score = hits[0].get("score", 0.0)
        second_score = hits[1].get("score", 0.0) or 1e-9

        # Two-tier gating: at high retrieval quality (both scores
        # excellent), close ratios are expected and normal - use an
        # absolute gap instead.  At lower quality, the ratio-based
        # gate prevents synthesis on genuinely ambiguous retrievals.
        if top_score >= 3.0:
            dominant = (top_score - second_score) >= 0.5
        else:
            dominant = (top_score / second_score) >= _DOMINANCE_RATIO

        if not dominant and not force_synthesize:
            # Enrich top hits with substantive excerpts so the agent has
            # real material to ground in (not one-line summaries).
            await _enrich_gated_excerpts(hits, ctx)
            return {
                "answer": "",
                "citations": [],
                "confidence": "low",
                "fallback_targets": fallback_targets,
                "retrieval": hits[:_GATED_RETURN_HITS],
                **_compression_stats,
                "note": (
                    "Multiple plausible candidates - synthesis skipped to "
                    "avoid anchoring on a wrong frame. Each retrieval entry "
                    "includes an excerpt from the page; read them and pick "
                    "the one that actually answers the question."
                ),
                "_meta": _build_meta(
                    timing_ms=(time.perf_counter() - t0) * 1000,
                    hint=_answer_hint("low", len(hits)),
                    extra={"hyde_used": _hyde_used},
                ),
            }

    # Confidence is the only axis we gate on. We deliberately do NOT add a
    # second gate keyed on question shape (e.g. relational questions
    # containing connectives like "between", "and", "from"). Relational vs
    # non-relational is the wrong axis to gate on: the hard relational
    # failures already surface as low-dominance retrievals and are caught
    # by the gate above, while a shape-based gate over-fires on confidently
    # dominant relational questions and pushes cost back onto the agent's
    # own reasoning loop.

    # --- Synthesis (LLM) ---------------------------------------------------
    provider = (
        _provider_early
        if (_hyde_viable and _provider_early is not None)
        else _resolve_provider_for_answer(getattr(ctx, "path", None))
    )
    if provider is None:
        # Retrieval-only mode (no provider). Return the hits so the agent can
        # at least skip the search_codebase step.
        return {
            "answer": "",
            "citations": [],
            "confidence": "low",
            "fallback_targets": fallback_targets,
            "retrieval": hits,
            **_compression_stats,
            "note": (
                "No LLM provider configured (set PROVENANT_PROVIDER + API key). "
                "Returning retrieval hits only - Read the listed files to answer."
            ),
            "_meta": _build_meta(
                timing_ms=(time.perf_counter() - t0) * 1000,
                hint=_answer_hint("low", len(hits)),
            ),
        }

    user_prompt = _USER_TEMPLATE.format(
        question=question.strip(),
        n=len(hits),
        context=_build_context_block(hits, question=question, compress=compress),
    )

    answer_text = ""
    _tokens_in = 0
    _tokens_out = 0
    try:
        response = await asyncio.wait_for(
            provider.generate(
                system_prompt=_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                max_tokens=1024,
                temperature=0.2,
            ),
            timeout=30.0,
        )
        answer_text = (response.content or "").strip()
        _tokens_in = getattr(response, "input_tokens", 0) or 0
        _tokens_out = getattr(response, "output_tokens", 0) or 0
    except Exception as exc:
        _log.warning("get_answer LLM call failed: %s", exc)
        return {
            "answer": "",
            "citations": [],
            "confidence": "low",
            "fallback_targets": fallback_targets,
            "retrieval": hits,
            **_compression_stats,
            "note": f"LLM synthesis failed ({type(exc).__name__}). Read the listed files to answer.",
            "_meta": _build_meta(
                timing_ms=(time.perf_counter() - t0) * 1000,
                hint=_answer_hint("low", len(hits)),
            ),
        }

    citations = [
        h["target_path"] for h in hits if h["target_path"] and h["target_path"] in answer_text
    ]
    if not citations:
        # Fall back to top-2 retrieval paths so the agent always has something to verify.
        citations = fallback_targets[:2]

    # Post-synthesis pruning disabled: wiki retrieval already returns few pages,
    # pruning one page saves <1% tokens but measurably reduces answer quality.

    # Compute confidence from the dominance ratio (top hit vs second hit).
    # The dominance ratio is a more reliable separator than absolute BM25
    # thresholds, which tend to label most retrievals "high" indiscriminately.
    if len(hits) >= 2:
        _top = hits[0].get("score", 0.0)
        _second = hits[1].get("score", 0.0) or 1e-9
        _ratio = _top / _second
    else:
        _ratio = float("inf") if hits else 0.0
    if _ratio >= _DOMINANCE_RATIO:
        confidence = "high"
    else:
        confidence = "medium"

    # Second gate: downgrade when the LLM's own answer admits insufficiency.
    # Retrieval dominance only tells us we indexed the right file; it does
    # not mean the synthesized text is usable. Shipping a hedged answer with
    # confidence="high" misleads the consumer AND drags the full retrieval
    # payload (~10k chars) through the conversation cache for no benefit.
    hedged = _answer_is_hedged(answer_text)
    if hedged:
        confidence = "low"

    # Third gate - identifier-citation gate: when the question explicitly
    # names identifiers (classes / methods / snake_case / CamelCase) and
    # NONE of the top retrieval hits contain any of those identifiers as a
    # hydrated symbol, retrieval may be pointing at plausible-but-wrong
    # files (same module family, similar vocabulary). Downgrade high->medium
    # so the consumer Reads the `fallback_targets`. Only applies when the
    # question actually names identifiers - mechanism-descriptive questions
    # (no symbol names) are unaffected.
    if confidence == "high" and question_ids:
        top_n = [h for h in hits[:_ENRICH_TOP_N_HITS] if h.get("symbols")]
        has_match = any(
            s.get("_matched") for h in top_n for s in (h.get("symbols") or [])
        )
        if not has_match:
            confidence = "medium"

    if hedged:
        # Hedged answers: drop the retrieval payload. The consumer has been
        # told to read the source - the symbol-docstring blob that helped
        # synthesis doesn't help them, and keeping it in the response bloats
        # every follow-up turn's prompt cache.
        payload = {
            "answer": answer_text,
            "citations": citations,
            "confidence": "low",
            "fallback_targets": fallback_targets[:3],
            "retrieval": [],
            "note": (
                "Synthesis hedged: the LLM could not ground the question in "
                "the indexed wiki. Read one of fallback_targets to answer."
            ),
        }
    else:
        payload = {
            "answer": answer_text,
            "citations": citations,
            "confidence": confidence,
            "fallback_targets": fallback_targets,
            "retrieval": hits,
        }
        if confidence == "high":
            payload["note"] = (
                "High confidence: top retrieval result clearly dominates "
                f"(dominance ratio {_ratio:.2f}x) AND the synthesized answer "
                "is direct (no hedging). Cite this answer; do not re-read the "
                "source unless a specific detail is missing."
            )

    payload.update(_compression_stats)

    # Compute and attach attribution confidence score.
    # citation_density = fraction of retrieved pages actually cited in the answer.
    # This is a zero-cost grounding signal: high → synthesis is grounded;
    # low → LLM filled gaps from weights, answer may be unreliable.
    _attr_confidence = _compute_attribution_confidence(
        citations, fallback_targets
    )
    payload["attribution_confidence"] = round(_attr_confidence, 3)

    # Log for provenant improve — low-confidence events are the training signal
    # for targeted wiki page re-generation.
    _repo_path_str = str(ctx.path) if getattr(ctx, "path", None) else getattr(ctx, "_repo_path", None)

    _log_confidence(
        repo_path=_repo_path_str,
        question=question,
        confidence_score=_attr_confidence,
        citations=citations,
        fallback_targets=fallback_targets,
        confidence_label=confidence,
    )

    # Auto-repair: when confidence is low AND we have a provider + repo path,
    # fire a background task that rewrites the uncited pages immediately.
    # The task is non-blocking — the caller gets the response instantly.
    # Next time a similar query arrives, the improved pages will be cited.
    if (
        _attr_confidence < _AUTO_REPAIR_THRESHOLD
        and _repo_path_str
        and provider is not None
        and fallback_targets
    ):
        _uncited = [
            t for t in fallback_targets
            if Path(t).as_posix().lower() not in
            {Path(c).as_posix().lower() for c in citations}
        ]
        if _uncited:
            with contextlib.suppress(Exception):
                asyncio.create_task(
                    _background_repair(
                        repo_path=_repo_path_str,
                        uncited_pages=_uncited,
                        session_factory=ctx.session_factory,
                        provider=provider,
                    )
                )

    # Persist to cache. Best-effort: cache failures must NEVER block the
    # response (we already have the answer in hand).
    if answer_text:
        with contextlib.suppress(Exception):
            async with get_session(ctx.session_factory) as session:
                row = AnswerCache(
                    repository_id=repo_id,
                    question_hash=qhash,
                    question=question.strip(),
                    payload_json=_json.dumps(payload),
                    provider_name=getattr(provider, "provider_name", "") or "",
                    model_name=getattr(provider, "model_name", "") or "",
                )
                session.add(row)
                await session.commit()

    _elapsed_ms = round((time.perf_counter() - t0) * 1000)
    payload["_meta"] = _build_meta(
        timing_ms=_elapsed_ms,
        hint=_answer_hint(confidence, len(hits)),
        extra={"tokens_in": _tokens_in, "tokens_out": _tokens_out, "hyde_used": _hyde_used},
    )

    return payload
