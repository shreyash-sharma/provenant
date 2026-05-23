"""``provenant improve`` — self-healing index repair via attribution feedback.

Reads .provenant/confidence_log.jsonl (written by provenant_ask after each
synthesis), identifies wiki pages that were repeatedly retrieved but never
cited in answers (low-attribution pages), and regenerates only those pages.

This closes the feedback loop:

    query → retrieve → synthesize → attribution_confidence
                                            ↓ (if low)
                                    log uncited pages
                                            ↓
                              provenant improve (re-gen weak pages)
                                            ↓
                              next similar query → higher confidence

The result is a self-improving index: usage automatically surfaces gaps,
and improvement is surgical (only weak pages are regenerated, not the
full index).
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from pathlib import Path

import click
from rich.table import Table

from provenant.cli.helpers import (
    console,
    ensure_provenant_dir,
    get_db_url_for_repo,
    resolve_repo_path,
    run_async,
)


# A page is a "weak" candidate if it was retrieved at least this many times
# without ever being cited.
_MIN_RETRIEVALS = 3
# Fraction of retrievals that resulted in a citation below which we flag weak.
_WEAK_CITATION_RATE = 0.25


@click.command("improve")
@click.argument("path", required=False, default=None)
@click.option(
    "--min-retrievals",
    type=int,
    default=_MIN_RETRIEVALS,
    help="Minimum times a page must be retrieved to be considered for repair.",
)
@click.option(
    "--weak-threshold",
    type=float,
    default=_WEAK_CITATION_RATE,
    help="Citation rate below which a page is flagged as weak (0–1).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Show which pages would be repaired without regenerating.",
)
@click.option(
    "--top-n",
    type=int,
    default=10,
    help="Repair at most this many weak pages per run.",
)
def improve_command(
    path: str | None,
    min_retrievals: int,
    weak_threshold: float,
    dry_run: bool,
    top_n: int,
) -> None:
    """Repair weak wiki pages using attribution feedback.

    Reads the confidence log written by provenant_ask, finds wiki pages that
    were consistently retrieved but not cited (low attribution), and
    regenerates them. Run this periodically to close the feedback loop:
    low-confidence queries automatically surface which pages need improvement.
    """
    repo_path = resolve_repo_path(path)
    ensure_provenant_dir(repo_path)

    from provenant.cli.ui import load_dotenv
    load_dotenv(repo_path)

    run_async(_improve(repo_path, min_retrievals, weak_threshold, dry_run, top_n))


async def _improve(
    repo_path: Path,
    min_retrievals: int,
    weak_threshold: float,
    dry_run: bool,
    top_n: int,
) -> None:
    log_path = Path(repo_path) / ".provenant" / "confidence_log.jsonl"

    if not log_path.exists():
        console.print(
            "[yellow]No confidence log found.[/yellow] "
            "Run some queries via provenant_ask first — low-confidence events "
            "are automatically logged to .provenant/confidence_log.jsonl."
        )
        return

    # --- Parse confidence log ---
    records = []
    with open(log_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    if not records:
        console.print("[yellow]Confidence log is empty.[/yellow]")
        return

    console.print(f"[bold]Confidence log:[/bold] {len(records)} entries")

    # --- Compute per-page stats ---
    # page_path → {retrieved_count, cited_count}
    page_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"retrieved": 0, "cited": 0})

    for rec in records:
        retrieved = rec.get("retrieved", [])
        citations = {Path(c).as_posix().lower() for c in rec.get("citations", [])}
        for page in retrieved:
            key = Path(page).as_posix().lower()
            page_stats[key]["retrieved"] += 1
            if key in citations:
                page_stats[key]["cited"] += 1

    # --- Identify weak pages ---
    weak_pages: list[tuple[str, float, int]] = []  # (path, citation_rate, retrievals)
    for page, stats in page_stats.items():
        n = stats["retrieved"]
        if n < min_retrievals:
            continue
        rate = stats["cited"] / n
        if rate < weak_threshold:
            weak_pages.append((page, rate, n))

    # Sort by citation rate ascending (worst first), then by retrieval count
    weak_pages.sort(key=lambda x: (x[1], -x[2]))
    weak_pages = weak_pages[:top_n]

    if not weak_pages:
        console.print(
            f"[green]No weak pages found[/green] (min_retrievals={min_retrievals}, "
            f"weak_threshold={weak_threshold:.0%}). Index looks healthy."
        )
        _print_summary(records, page_stats)
        return

    # --- Display weak pages ---
    table = Table(title="Weak Wiki Pages — Candidates for Repair", show_header=True)
    table.add_column("Page", style="cyan")
    table.add_column("Retrieved", justify="right")
    table.add_column("Cited", justify="right")
    table.add_column("Citation Rate", justify="right")
    table.add_column("Status", justify="center")

    for page, rate, n_retrieved in weak_pages:
        cited_n = page_stats[page]["cited"]
        status = "[red]WEAK[/red]" if rate < 0.1 else "[yellow]LOW[/yellow]"
        table.add_row(page, str(n_retrieved), str(cited_n), f"{rate:.0%}", status)

    console.print(table)

    if dry_run:
        console.print(
            f"\n[yellow]Dry run:[/yellow] would repair {len(weak_pages)} pages. "
            "Re-run without --dry-run to regenerate."
        )
        return

    # --- Regenerate weak pages ---
    console.print(f"\n[bold]Regenerating {len(weak_pages)} weak pages...[/bold]")
    await _regenerate_pages(repo_path, [p for p, _, _ in weak_pages], page_stats=page_stats)

    # --- Mark repaired in log (append a repair record) ---
    repair_record = {
        "ts": time.time(),
        "event": "repair",
        "pages_repaired": [p for p, _, _ in weak_pages],
        "weak_threshold": weak_threshold,
    }
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(repair_record) + "\n")

    console.print(
        f"\n[bold green]Done![/bold green] Repaired {len(weak_pages)} wiki pages. "
        "Run your queries again to measure confidence improvement."
    )


async def _regenerate_pages(
    repo_path: Path,
    page_paths: list[str],
    page_stats: dict[str, dict[str, int]] | None = None,
) -> None:
    """Regenerate wiki pages using attribution-aware prompts.

    Instead of the full ingestion pipeline (which requires a parsed AST and
    graph context), we use a targeted repair prompt that tells the LLM *why*
    the page is weak — it was retrieved but never cited. This is both simpler
    and more principled: the attribution signal is used directly in the repair.
    """
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from provenant.core.persistence.database import init_db
    from provenant.core.persistence.models import Page
    from provenant.cli.helpers import resolve_provider

    db_url = get_db_url_for_repo(repo_path)
    connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}
    engine = create_async_engine(db_url, connect_args=connect_args)
    await init_db(engine)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    provider = resolve_provider(None, None, repo_path)
    if not provider:
        console.print(
            "[red]No LLM provider configured.[/red] "
            "Set OPENAI_API_KEY or ANTHROPIC_API_KEY in .provenant/.env"
        )
        await engine.dispose()
        return

    _SYSTEM = (
        "You are Provenant, a codebase intelligence engine. "
        "Rewrite the given wiki page so it is more precise and retrieval-specific. "
        "The page has been retrieved repeatedly but never cited — it is too generic. "
        "Focus on: (1) the file's exact architectural role, (2) specific public APIs "
        "with their signatures, (3) which concrete problems this file solves. "
        "Use concrete names from the source. No preamble, no hedging. "
        "Return ONLY the improved markdown wiki page."
    )

    repaired = 0
    failed = 0

    for page_path in page_paths:
        # ── 1. Load existing DB record ──────────────────────────────────────
        async with factory() as session:
            result = await session.execute(
                select(Page).where(Page.target_path == page_path)
            )
            existing = result.scalars().first()
            if not existing:
                # Try normalized path / substring match
                result = await session.execute(
                    select(Page).where(Page.target_path.ilike(f"%{Path(page_path).name}%"))
                )
                existing = result.scalars().first()

        if not existing:
            console.print(f"  [yellow]Skip[/yellow] {page_path} — no DB record found")
            continue

        # ── 2. Read source file ─────────────────────────────────────────────
        abs_path = Path(repo_path) / page_path
        if not abs_path.exists():
            candidates = list(Path(repo_path).rglob(Path(page_path).name))
            if candidates:
                abs_path = candidates[0]
            else:
                console.print(f"  [yellow]Skip[/yellow] {page_path} — source file not found")
                continue

        try:
            source_text = abs_path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            console.print(f"  [yellow]Skip[/yellow] {page_path} — cannot read source: {exc}")
            continue

        # ── 3. Build attribution-aware repair prompt ────────────────────────
        stats = (page_stats or {}).get(page_path, {})
        retrieved_n = stats.get("retrieved", 0)
        cited_n = stats.get("cited", 0)
        rate_pct = int(cited_n / retrieved_n * 100) if retrieved_n else 0

        user_prompt = (
            f"## Attribution feedback\n"
            f"File: `{page_path}`\n"
            f"Retrieved: {retrieved_n} times | Cited: {cited_n} times ({rate_pct}% citation rate)\n"
            f"The low citation rate means this page is retrieved for relevant queries "
            f"but the synthesized answer never references it — the page content is "
            f"too generic or misses the key concepts that make this file useful.\n\n"
            f"## Current wiki page\n"
            f"{existing.content or '(no content)'}\n\n"
            f"## Source file (first 4000 chars)\n"
            f"```\n{source_text[:4000]}\n```\n\n"
            f"Rewrite the wiki page to be more precise and query-grounded. "
            f"Every sentence must help an LLM answer questions about this file. "
            f"Return ONLY the improved markdown."
        )

        try:
            response = await provider.generate(
                system_prompt=_SYSTEM,
                user_prompt=user_prompt,
                max_tokens=1500,
                temperature=0.2,
            )
            new_content = (response.content or "").strip()
            if not new_content:
                failed += 1
                console.print(f"  [red]FAIL[/red] {page_path} -- provider returned empty")
                continue

            # Extract a one-line summary from first non-empty line
            first_line = next(
                (ln.lstrip("# ").strip() for ln in new_content.splitlines() if ln.strip()),
                existing.summary or existing.title or page_path,
            )
            new_summary = first_line[:200]

            async with factory() as session:
                existing_db = await session.get(Page, existing.id)
                if existing_db:
                    existing_db.content = new_content
                    existing_db.summary = new_summary
                    await session.commit()

            repaired += 1
            console.print(f"  [green]OK[/green] {page_path}")

        except Exception as exc:
            failed += 1
            console.print(f"  [red]FAIL[/red] {page_path} -- {exc}")

    await engine.dispose()
    console.print(f"\nRepaired: {repaired}  Failed: {failed}")


def _print_summary(records: list[dict], page_stats: dict[str, dict]) -> None:
    """Print a brief summary of the confidence log."""
    if not records:
        return
    scores = [r.get("confidence_score", 0) for r in records if "confidence_score" in r]
    if not scores:
        return
    avg = sum(scores) / len(scores)
    low = sum(1 for s in scores if s < 0.3)
    console.print(
        f"\n[bold]Confidence log summary:[/bold] {len(scores)} queries  "
        f"avg={avg:.2f}  low_confidence={low} ({low/len(scores):.0%})"
    )


def analyze_confidence_log(repo_path: Path) -> dict:
    """Public helper: read confidence log and return calibration data.

    Used by eval scripts to measure confidence vs correctness correlation.
    Returns dict with per-record confidence scores and metadata.
    """
    log_path = Path(repo_path) / ".provenant" / "confidence_log.jsonl"
    if not log_path.exists():
        return {"records": [], "page_stats": {}}

    records = []
    with open(log_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    r = json.loads(line)
                    if "event" not in r:  # skip repair records
                        records.append(r)
                except json.JSONDecodeError:
                    pass

    page_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"retrieved": 0, "cited": 0})
    for rec in records:
        retrieved = rec.get("retrieved", [])
        citations = {Path(c).as_posix().lower() for c in rec.get("citations", [])}
        for page in retrieved:
            key = Path(page).as_posix().lower()
            page_stats[key]["retrieved"] += 1
            if key in citations:
                page_stats[key]["cited"] += 1

    return {"records": records, "page_stats": dict(page_stats)}
