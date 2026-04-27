"""CLI entry point — typer-based, backward-compatible flags."""
from __future__ import annotations

import datetime as dt
import json
import logging
import sys
import textwrap
from pathlib import Path
from typing import Optional

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.text import Text

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s · %(levelname)s · %(name)s · %(message)s",
)

app = typer.Typer(name="storytelling_bot", add_completion=False, help="Storytelling Data Lake Bot")
console = Console()


def _render_summary(state) -> str:
    from storytelling_bot.schema import LAYER_LABEL
    lines = [
        "=" * 78,
        f"STORYTELLING DATA LAKE — {state.entity_id.upper()}",
        "=" * 78,
        f"Coverage: {state.metrics.get('coverage_pct')}% · "
        f"Facts: {state.metrics.get('fact_count')} "
        f"(green={state.metrics.get('green_count')}, "
        f"red={state.metrics.get('red_count')}, "
        f"grey={state.metrics.get('grey_count')})",
        f"Freshness P50: {state.metrics.get('freshness_days_p50')} дн.",
        "",
        f"DECISION: {state.decision.get('recommendation', '?').upper()}",
        f"  rationale: {state.decision.get('rationale', '')}",
        f"  human_approval_required: {state.decision.get('human_approval_required')}",
        "",
        "--- TIMELINE ---",
    ]
    for ev in state.timeline:
        lines.append(f"  {ev['date']} · {ev['entity']} · {ev['layer']}")
        lines.append(f"      {textwrap.shorten(ev['text'], 110)}")
    lines += ["", "--- STORY (по слоям) ---"]
    for layer_name, subs in state.story.items():
        lines.append(f"\n■ {layer_name}")
        for sub, narrative in subs.items():
            lines.append(f"  ▸ {sub}")
            for ln in narrative.splitlines():
                lines.append(f"    {ln}")
    return "\n".join(lines)


def _build_payload(state) -> dict:
    payload = state.metrics.get("_payload")
    if payload:
        # Remove internal key before returning
        clean_metrics = {k: v for k, v in state.metrics.items() if k != "_payload"}
        payload = {**payload, "metrics": clean_metrics}
    else:
        payload = {
            "entity_id": state.entity_id,
            "generated_at": dt.datetime.now(dt.UTC).isoformat(),
            "metrics": state.metrics,
            "decision": state.decision,
            "timeline": state.timeline,
            "story": state.story,
            "facts": [f.to_jsonable() for f in state.facts],
        }
    return payload


@app.command("run")
def cmd_run(
    entity: str = typer.Option("accumulator", "--entity", "-e", help="Entity ID"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="JSON report path"),
    export_html: Optional[Path] = typer.Option(None, "--export-html", help="HTML dashboard path"),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    """Run full pipeline for an entity."""
    from storytelling_bot.collectors.base import DEMO_CORPUS
    from storytelling_bot.graph import build_graph
    from storytelling_bot.schema import State

    if entity not in DEMO_CORPUS:
        # Allow unknown entities for real collectors (Task 4+)
        console.print(f"[yellow]Warning: '{entity}' not in demo corpus — collectors may return 0 chunks[/yellow]")

    state = State(entity_id=entity, report_path=str(output) if output else None)
    graph = build_graph()
    final = graph.run(state)

    payload = _build_payload(final)

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        clean_payload = {k: v for k, v in payload.items() if k != "_payload"}
        output.write_text(json.dumps(clean_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        console.print(f"[green]Report saved → {output}[/green]")

    if export_html:
        from storytelling_bot.dashboard import export_html as do_export
        export_html.parent.mkdir(parents=True, exist_ok=True)
        do_export(payload, entity, str(export_html))
        console.print(f"[green]Dashboard saved → {export_html}[/green]")

    if not quiet:
        print(_render_summary(final))


@app.command("list")
def cmd_list() -> None:
    """List entities in watchlist."""
    from storytelling_bot.collectors.base import DEMO_CORPUS
    console.print("Сущности в watchlist:")
    for ent, chunks in DEMO_CORPUS.items():
        console.print(f"  · {ent}  ({len(chunks)} сырых фрагментов)")


@app.command("add-fact")
def cmd_add_fact(
    entity: str = typer.Option(..., "--entity", "-e"),
    text: str = typer.Option(..., "--text", help="Fact text"),
    source: str = typer.Option("offline_interview", "--source", "--add-fact-source"),
    url: str = typer.Option("internal://manual", "--url", "--add-fact-url"),
) -> None:
    """Add an offline fact to the corpus."""
    from storytelling_bot.collectors.offline import OfflineIngest
    OfflineIngest().add_fact(entity, text, url)
    console.print(f"[green]Fact added for {entity}[/green]")


@app.command("diff")
def cmd_diff(
    prev: Path = typer.Argument(...),
    curr: Path = typer.Argument(...),
) -> None:
    """Compare two JSON reports."""
    p = json.loads(prev.read_text(encoding="utf-8"))
    c = json.loads(curr.read_text(encoding="utf-8"))

    def key(f):
        return f"{f['source_url']}::{hash(f['text'])}"

    prev_keys = {key(f) for f in p.get("facts", [])}
    curr_keys = {key(f) for f in c.get("facts", [])}
    added = [f for f in c["facts"] if key(f) not in prev_keys]
    removed = [f for f in p["facts"] if key(f) not in curr_keys]

    console.print(f"=== DIFF {prev} → {curr} ===")
    console.print(f"Decision: {p['decision'].get('recommendation')} → {c['decision'].get('recommendation')}")
    console.print(f"+ {len(added)} новых фактов, − {len(removed)} убрано")
    for f in added[:10]:
        console.print(f"  + [{f['flag']}] {textwrap.shorten(f['text'], 100)}")
    for f in removed[:10]:
        console.print(f"  − [{f['flag']}] {textwrap.shorten(f['text'], 100)}")


@app.command("watch")
def cmd_watch(
    entity: str = typer.Option("accumulator", "--entity", "-e"),
    interval: int = typer.Option(30, "--interval"),
    max_iter: int = typer.Option(3, "--max-iter"),
) -> None:
    """Watch mode — periodic re-run with alerts."""
    import time
    from storytelling_bot.graph import build_graph
    from storytelling_bot.schema import State

    console.print(f"[bold]WATCH mode:[/bold] checking every {interval}s (max {max_iter} cycles)")
    last = 0
    for i in range(max_iter):
        state = State(entity_id=entity)
        final = build_graph().run(state)
        n = len(final.facts)
        delta = n - last
        rec = final.decision.get("recommendation", "?").upper()
        console.print(f"[tick {i+1}] facts={n} (Δ={delta:+d}), decision={rec}")
        if delta > 0 and i > 0:
            console.print(f"[bold yellow]⚠ ALERT (mock): {delta} new fact(s) for {entity}[/bold yellow]")
        last = n
        if i < max_iter - 1:
            time.sleep(interval)


@app.command("export-html")
def cmd_export_html(
    report: Path = typer.Argument(..., help="JSON report"),
    output: Path = typer.Option(Path("dashboard.html"), "--output", "-o"),
) -> None:
    """Export existing JSON report to HTML dashboard."""
    from storytelling_bot.dashboard import export_html
    payload = json.loads(report.read_text(encoding="utf-8"))
    export_html(payload, payload.get("entity_id", "unknown"), str(output))
    console.print(f"[green]Dashboard → {output}[/green]")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
