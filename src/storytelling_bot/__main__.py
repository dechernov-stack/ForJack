"""CLI entry point — typer-based, backward-compatible flags."""
from __future__ import annotations

import datetime as dt
import json
import logging
import textwrap
from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s · %(levelname)s · %(name)s · %(message)s",
)

app = typer.Typer(name="storytelling_bot", add_completion=False, help="Storytelling Data Lake Bot")
console = Console()


def _render_summary(state) -> str:
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
        for sub, block in subs.items():
            lines.append(f"  ▸ {sub}")
            if isinstance(block, dict):
                if block.get("thesis"):
                    lines.append(f"    ТЕЗИС: {textwrap.shorten(block['thesis'], 120)}")
                for ev in block.get("evidence", [])[:2]:
                    lines.append(f"    · [{ev.get('flag','?')}] {textwrap.shorten(ev.get('text',''), 100)}")
            else:
                for ln in str(block).splitlines():
                    lines.append(f"    {ln}")
    if state.cross_layer_overview:
        lines += ["", "--- CROSS-LAYER OVERVIEW ---", state.cross_layer_overview]
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
    output: Path | None = typer.Option(None, "--output", "-o", help="JSON report path"),
    export_html: Path | None = typer.Option(None, "--export-html", help="HTML dashboard path"),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
    profile_path: Path | None = typer.Option(None, "--profile", help="ExpertProfile JSON path"),
    hypothesis: str | None = typer.Option(None, "--hypothesis", help="Override profile hypothesis"),
    voice: str | None = typer.Option(None, "--voice", help="Override profile voice"),
    save_profile: Path | None = typer.Option(None, "--save-profile", help="Save resolved profile to path"),
) -> None:
    """Run full pipeline for an entity."""
    from storytelling_bot.collectors.base import DEMO_CORPUS
    from storytelling_bot.expert.profile import default_profile_for, load_profile
    from storytelling_bot.expert.profile import save_profile as _save_profile
    from storytelling_bot.graph import build_graph
    from storytelling_bot.schema import State

    if entity not in DEMO_CORPUS:
        # Allow unknown entities for real collectors (Task 4+)
        console.print(f"[yellow]Warning: '{entity}' not in demo corpus — collectors may return 0 chunks[/yellow]")

    if profile_path:
        expert_profile = load_profile(profile_path)
    else:
        expert_profile = default_profile_for(entity)

    if hypothesis:
        expert_profile = expert_profile.model_copy(update={"hypothesis": hypothesis})
    if voice:
        expert_profile = expert_profile.model_copy(update={"voice": voice})

    if save_profile:
        _save_profile(expert_profile, save_profile)
        console.print(f"[green]Profile saved → {save_profile}[/green]")

    state = State(entity_id=entity, report_path=str(output) if output else None, expert_profile=expert_profile)
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
def cmd_list(
    watchlist: bool = typer.Option(False, "--watchlist", help="Read from data/watchlist.json"),
) -> None:
    """List entities in watchlist."""
    import os

    wl_path = Path(os.environ.get("WATCHLIST_PATH", "data/watchlist.json"))

    if watchlist or wl_path.exists():
        if wl_path.exists():
            data = json.loads(wl_path.read_text(encoding="utf-8"))
            entities = data.get("entities", [])
            console.print(f"[bold]Watchlist[/bold] ({wl_path}, {len(entities)} entities):")
            for e in entities:
                kind = e.get("kind", "company")
                name = e.get("display_name", e["id"])
                added = e.get("added_at", "?")
                notes = e.get("notes", "")
                console.print(f"  · [cyan]{e['id']}[/cyan]  [{kind}]  {name}  (added {added})")
                if notes:
                    console.print(f"      {notes}")
            return
        console.print(f"[yellow]Watchlist file not found: {wl_path}[/yellow]")

    from storytelling_bot.collectors.base import DEMO_CORPUS
    console.print("Сущности в demo corpus:")
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


@app.command("search")
def cmd_search(
    entity: str = typer.Option(..., "--entity", "-e", help="Entity ID to search within"),
    query: str = typer.Option(..., "--query", "-q", help="Semantic search query"),
    top: int = typer.Option(5, "--top", help="Number of results"),
) -> None:
    """Semantic search over indexed facts for an entity."""
    from storytelling_bot.llm import get_llm_client
    from storytelling_bot.storage.vector_store import VectorStore

    llm = get_llm_client()
    vs = VectorStore()

    try:
        vectors = llm.embed([query])
    except Exception as exc:
        console.print(f"[red]Embed failed: {exc}[/red]")
        raise typer.Exit(1)

    results = vs.search_with_filter(vectors[0], entity_id=entity, limit=top, min_score=0.0)

    if not results:
        console.print(f"[yellow]No facts found for '{entity}' matching '{query}'[/yellow]")
        return

    console.print(f"\n[bold]Top {len(results)} facts for '{entity}' — query: '{query}'[/bold]\n")
    for i, r in enumerate(results, 1):
        score = r.get("_score", 0)
        flag = r.get("flag", "?")
        text = r.get("text", "")[:120]
        url = r.get("source_url", "")
        layer = r.get("layer", "?")
        console.print(f"  {i}. [score={score:.3f}] [layer={layer}] [{flag}]")
        console.print(f"     {text}")
        console.print(f"     {url}\n")


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


@app.command("profile")
def cmd_profile(
    entity: str = typer.Option("accumulator", "--entity", "-e", help="Entity ID"),
    goal: str | None = typer.Option(None, "--goal", "-g", help="Goal preset: business|personality|politics|impact"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Save profile JSON to path"),
    show: bool = typer.Option(True, "--show/--no-show", help="Print profile to console"),
) -> None:
    """Show or generate an ExpertProfile for an entity."""
    from storytelling_bot.expert.profile import default_profile_for, default_profile_for_goal, save_profile

    if goal:
        p = default_profile_for_goal(goal)
    else:
        p = default_profile_for(entity)

    if output:
        save_profile(p, output)
        console.print(f"[green]Profile saved → {output}[/green]")

    if show:
        console.print(f"[bold]ExpertProfile[/bold] — {p.analyst_name} ({p.role})")
        console.print(f"  Hypothesis: {p.hypothesis[:120]}")
        console.print(f"  Voice: {p.voice[:80]}")
        console.print(f"  Priority layers: {[lay.name for lay in p.priority_layers]}")
        console.print(f"  keep_threshold: {p.keep_threshold}  min_kept_per_subcat: {p.min_kept_per_subcat}")
        if p.taboo_topics:
            console.print(f"  Taboo topics: {p.taboo_topics}")


@app.command("serve")
def cmd_serve(
    host: str = typer.Option("0.0.0.0", "--host", help="Bind host"),
    port: int = typer.Option(8000, "--port", help="Bind port"),
    reload: bool = typer.Option(False, "--reload", help="Auto-reload on code changes"),
) -> None:
    """Start the FastAPI REST API server."""
    import uvicorn

    from storytelling_bot.api import app as fastapi_app
    if reload:
        uvicorn.run("storytelling_bot.api:app", host=host, port=port, reload=True)
    else:
        uvicorn.run(fastapi_app, host=host, port=port)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
