#!/usr/bin/env python3
"""Generate a standalone HTML dashboard artifact from dashboard_data.json.

This is a run artifact publisher. It does not read row-level persona files,
choice files, or LLM responses. It embeds the current run's dashboard_data.json
inside a self-contained HTML file so the run folder has an immediately openable
dashboard artifact.
"""

from __future__ import annotations

import argparse
import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HTML_GENERATOR_VERSION = "0.1.0"


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object in {path}")
    return value


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def resolve_output(manifest: dict[str, Any], key: str, run_dir: Path, fallback: str) -> Path:
    outputs = manifest.get("outputs", {}) if isinstance(manifest.get("outputs"), dict) else {}
    raw = outputs.get(key)
    if isinstance(raw, str) and raw:
        return Path(raw)
    return run_dir / fallback


def format_json_for_script(data: dict[str, Any]) -> str:
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return raw.replace("</", "<\\/")


def choose_dashboard_data(manifest_path: Path | None, dashboard_data_path: Path | None) -> tuple[dict[str, Any], Path | None, Path]:
    if dashboard_data_path is not None:
        return load_json(dashboard_data_path), None, dashboard_data_path
    if manifest_path is None:
        raise ValueError("provide either --manifest or --dashboard-data")
    manifest = load_json(manifest_path)
    run_dir = manifest_path.resolve().parent
    data_path = resolve_output(manifest, "dashboard_data", run_dir, "dashboard_data.json")
    return load_json(data_path), manifest_path, data_path


def render_html(data: dict[str, Any], *, source_path: Path, manifest_path: Path | None) -> str:
    run = data.get("run", {}) if isinstance(data.get("run"), dict) else {}
    title = f"Synthetic Market Dashboard · {run.get('run_id') or 'run'}"
    data_script = format_json_for_script(data)
    generated_at = datetime.now(timezone.utc).isoformat()
    source = html.escape(str(source_path))
    manifest = html.escape(str(manifest_path)) if manifest_path else "—"
    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>{html.escape(title)}</title>
  <style>
    :root {{ color-scheme: dark; --bg:#05070d; --panel:rgba(14,18,32,.82); --line:rgba(255,255,255,.12); --text:#f8f9ff; --muted:#a9b1c8; --blue:#4f8cff; --cyan:#32d5ff; --violet:#a66cff; --amber:#ffbd66; --green:#47e6a3; --red:#ff6b8a; font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif; }}
    * {{ box-sizing:border-box; }} body {{ margin:0; background:radial-gradient(circle at top left,rgba(79,140,255,.22),transparent 34rem),radial-gradient(circle at top right,rgba(166,108,255,.18),transparent 30rem),linear-gradient(180deg,#05070d,#080b14 46%,#05070d); color:var(--text); }}
    body::before {{ content:\"\"; position:fixed; inset:0; pointer-events:none; background-image:linear-gradient(rgba(255,255,255,.055) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.045) 1px,transparent 1px); background-size:48px 48px; mask-image:linear-gradient(to bottom,#000,transparent 82%); }}
    main {{ position:relative; padding:32px clamp(20px,4vw,64px) 48px; }}
    .top {{ display:flex; align-items:center; justify-content:space-between; gap:18px; padding:14px 16px; border:1px solid var(--line); border-radius:999px; background:rgba(7,10,18,.62); backdrop-filter:blur(22px); }}
    .brand,.badge {{ display:inline-flex; align-items:center; gap:8px; }} .brand {{ font-weight:850; letter-spacing:-.02em; }} .badge {{ padding:9px 12px; border:1px solid var(--line); border-radius:999px; color:var(--muted); background:rgba(255,255,255,.06); }}
    .hero {{ display:grid; grid-template-columns:minmax(0,1fr) 420px; gap:56px; padding:86px 0 42px; align-items:end; }}
    .eyebrow {{ margin:0 0 12px; color:var(--cyan); text-transform:uppercase; letter-spacing:.16em; font-size:.76rem; font-weight:850; }}
    h1 {{ margin:0; max-width:960px; font-size:clamp(3rem,7vw,7rem); line-height:.9; letter-spacing:-.08em; }}
    .hero p {{ max-width:760px; color:var(--muted); font-size:1.08rem; line-height:1.65; }}
    .metrics {{ display:grid; gap:14px; }} .metric,.card {{ border:1px solid var(--line); background:linear-gradient(145deg,rgba(255,255,255,.09),rgba(255,255,255,.035)); border-radius:28px; box-shadow:0 28px 90px rgba(0,0,0,.42); backdrop-filter:blur(24px); }}
    .metric {{ padding:22px; }} .metric span {{ color:var(--muted); }} .metric strong {{ display:block; margin-top:7px; font-size:2.35rem; letter-spacing:-.06em; }}
    .grid4 {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:16px; margin:20px 0 82px; }}
    .section {{ margin:82px 0 0; }} .section h2 {{ margin:0 0 10px; font-size:clamp(2rem,4vw,4rem); line-height:.95; letter-spacing:-.06em; }} .section > p {{ color:var(--muted); max-width:820px; line-height:1.65; }}
    .two {{ display:grid; grid-template-columns:.85fr 1.15fr; gap:18px; }} .three {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:18px; }} .four {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:18px; }}
    .card {{ padding:24px; min-width:0; }} .card h3 {{ margin:0 0 14px; letter-spacing:-.035em; }} .muted {{ color:var(--muted); }}
    .barRow {{ margin:0 0 22px; }} .barTop {{ display:flex; justify-content:space-between; gap:18px; color:var(--muted); }} .barTrack {{ height:14px; margin-top:10px; background:rgba(255,255,255,.08); border-radius:999px; overflow:hidden; border:1px solid rgba(255,255,255,.08); }} .barFill {{ height:100%; border-radius:inherit; }}
    .pillRow {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:16px; }} .pill {{ padding:8px 10px; border:1px solid var(--line); border-radius:999px; color:var(--muted); background:rgba(255,255,255,.06); font-size:.8rem; }}
    .distRow,.auditRow,.reasonRow,.artifactRow {{ display:grid; grid-template-columns:1fr auto; gap:12px; padding:12px 0; border-bottom:1px solid rgba(255,255,255,.07); }} .distRow:last-child,.auditRow:last-child,.reasonRow:last-child,.artifactRow:last-child {{ border-bottom:0; }}
    .product strong {{ display:block; font-size:1.8rem; letter-spacing:-.05em; }} .outside {{ background:linear-gradient(145deg,rgba(255,189,102,.12),rgba(255,255,255,.035)); }}
    .case {{ min-height:290px; }} .choice {{ color:var(--cyan); font-size:1.35rem; font-weight:900; letter-spacing:-.04em; }}
    .warning {{ margin-top:20px; padding:16px; border:1px solid rgba(255,189,102,.26); border-radius:18px; background:rgba(255,189,102,.11); color:var(--amber); line-height:1.5; }}
    footer {{ margin-top:92px; padding-top:22px; border-top:1px solid var(--line); display:flex; justify-content:space-between; gap:16px; color:var(--muted); }}
    @media (max-width:1100px) {{ .hero,.two {{ grid-template-columns:1fr; }} .grid4,.four,.three {{ grid-template-columns:repeat(2,minmax(0,1fr)); }} }}
    @media (max-width:700px) {{ .top,footer {{ flex-direction:column; align-items:flex-start; }} .grid4,.four,.three {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
<script>window.DASHBOARD_DATA={data_script};</script>
<main id=\"app\"></main>
<script>
const data = window.DASHBOARD_DATA || {{}};
const choiceLabels = {{focal_product:'Focal product', competitor:'Competitor', none_or_delay:'None / delay'}};
const tones = {{focal_product:'var(--blue)', competitor:'var(--violet)', none_or_delay:'var(--amber)'}};
function esc(v) {{ return String(v ?? '—').replace(/[&<>\"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}}[c])); }}
function titleCase(v) {{ return esc(v).replaceAll('_',' ').replace(/\\b\\w/g, l => l.toUpperCase()); }}
function num(v) {{ const n=Number(v); return Number.isFinite(n)?new Intl.NumberFormat(undefined,{{maximumFractionDigits:0}}).format(n):'—'; }}
function compact(v) {{ const n=Number(v); return Number.isFinite(n)?new Intl.NumberFormat(undefined,{{notation:'compact',maximumFractionDigits:1}}).format(n):'—'; }}
function pct(v) {{ const n=Number(v); return Number.isFinite(n)?`${{(n*100).toFixed(1)}}%`:'—'; }}
function bars(rows) {{ return `<div>${{(rows||[]).map(r=>`<div class=\"barRow\"><div class=\"barTop\"><span>${{choiceLabels[r.choice]||titleCase(r.choice)}}</span><strong>${{pct(r.share)}}</strong></div><div class=\"barTrack\"><div class=\"barFill\" style=\"width:${{Math.max(0,Math.min(100,(Number(r.share)||0)*100))}}%;background:${{tones[r.choice]||'var(--cyan)'}}\"></div></div>${{r.p2_5!==undefined||r.p97_5!==undefined?`<small class=\"muted\">${{pct(r.p2_5)}} – ${{pct(r.p97_5)}} interval</small>`:''}}</div>`).join('')}}</div>`; }}
function pills(obj) {{ return `<div class=\"pillRow\">${{Object.entries(obj||{{}}).map(([k,v])=>`<span class=\"pill\">${{titleCase(k)}}: ${{titleCase(v)}}</span>`).join('')}}</div>`; }}
function distCard(name, rows) {{ return `<article class=\"card\"><h3>${{titleCase(name)}}</h3>${{(rows||[]).slice(0,6).map(r=>`<div class=\"distRow\"><div><strong>${{titleCase(r.value)}}</strong><br><span class=\"muted\">${{num(r.respondent_count)}} respondents</span></div><div><strong>${{pct(r.weighted_share)}}</strong><br><span class=\"muted\">${{compact(r.weighted_population)}}</span></div></div>`).join('')}}</article>`; }}
const run = data.run || {{}}; const method = data.method || {{}}; const panel = data.country_panel || {{}}; const results = data.results || {{}};
const app = document.getElementById('app');
app.innerHTML = `
  <nav class=\"top\"><span class=\"brand\">✦ Silicon Sampling</span><span class=\"badge\">Standalone dashboard.html</span></nav>
  <section class=\"hero\"><div><p class=\"eyebrow\">Census-weighted synthetic respondent panel</p><h1>Market choice intelligence without losing the research trail.</h1><p>Self-contained dashboard artifact generated from dashboard_data.json. It is a presentation layer only and does not read row-level personas, choice rows, or LLM responses.</p><div class=\"pillRow\"><span class=\"pill\">Run: ${{esc(run.run_id)}}</span><span class=\"pill\">Engine: ${{esc(method.interview_engine)}}</span><span class=\"pill\">Calibration: ${{esc(method.calibration_level)}}</span></div></div><div class=\"metrics\"><div class=\"metric\"><span>Respondents</span><strong>${{num(panel.respondent_count)}}</strong></div><div class=\"metric\"><span>Weighted population</span><strong>${{compact(panel.total_weighted_population)}}</strong></div><div class=\"metric\"><span>Choice records</span><strong>${{num(results.record_count)}}</strong></div></div></section>
  <section class=\"grid4\"><div class=\"metric\"><span>Dashboard data version</span><strong>${{esc(data.dashboard_data_version)}}</strong></div><div class=\"metric\"><span>Prompt/order</span><strong>${{esc(method.order_policy || '—')}}</strong></div><div class=\"metric\"><span>Archetypes</span><strong>${{num((data.archetypes||[]).length)}}</strong></div><div class=\"metric\"><span>Quality warnings</span><strong>${{num(data.quality?.llm_risk_summary?.warning_count || 0)}}</strong></div></section>
  <section class=\"section\"><p class=\"eyebrow\">01 · Market result</p><h2>Weighted choice shares</h2><p>The quantitative answer from the active country run. Intervals are shown when bootstrap artifacts are available.</p><div class=\"two\"><article class=\"card\">${{bars(results.choice_shares||[])}}</article><div class=\"three\">${{(data.product_scenario?.alternatives||[]).map(a=>`<article class=\"card product ${{a.is_outside_option?'outside':''}}\"><p class=\"eyebrow\">${{esc(a.id)}}</p><h3>${{esc(a.name)}}</h3><strong>${{a.is_outside_option?'Delay / no purchase':`${{num(a.price)}} ${{esc(a.currency||data.product_scenario?.currency||'')}}`}}</strong>${{pills(a.normalized_attributes)}}</article>`).join('')}}</div></div></section>
  <section class=\"section\"><p class=\"eyebrow\">02 · Country panel</p><h2>Weighted population structure</h2><p>Population distributions come from the active run's dashboard aggregate, not from a reusable static panel.</p><div class=\"three\">${{Object.entries(panel.distributions||{{}}).slice(0,6).map(([k,v])=>distCard(k,v)).join('')}}</div></section>
  <section class=\"section\"><p class=\"eyebrow\">03 · Archetypes</p><h2>Representative profiles</h2><div class=\"four\">${{(data.archetypes||[]).slice(0,8).map(a=>`<article class=\"card\"><h3>${{esc(a.label)}}</h3><p class=\"muted\">${{compact(a.weighted_population)}} people · ${{num(a.respondent_count)}} respondents · ${{pct(a.weighted_share)}}</p>${{pills(a.profile)}}${{bars(Object.entries(a.choice_shares||{{}}).map(([choice,share])=>({{choice,share}})))}}</article>`).join('')}}</div></section>
  <section class=\"section\"><p class=\"eyebrow\">04 · Reasons</p><h2>Drivers and barriers</h2><div class=\"three\"><article class=\"card\"><h3>Top drivers</h3>${{(results.top_drivers||[]).slice(0,8).map(x=>`<div class=\"reasonRow\"><strong>${{titleCase(x.label)}}</strong><span class=\"muted\">${{compact(x.weighted_count)}}</span></div>`).join('')}}</article><article class=\"card\"><h3>Top barriers</h3>${{(results.top_barriers||[]).slice(0,8).map(x=>`<div class=\"reasonRow\"><strong>${{titleCase(x.label)}}</strong><span class=\"muted\">${{compact(x.weighted_count)}}</span></div>`).join('')}}</article><article class=\"card\"><h3>Reason cubes</h3><p class=\"muted\">${{num((data.reason_cube||[]).length)}} segment/choice reason summaries retained.</p></article></div></section>
  <section class=\"section\"><p class=\"eyebrow\">05 · Audit</p><h2>Method and quality boundary</h2><div class=\"three\"><article class=\"card\"><h3>Method</h3>${{['interview_engine','calibration_level','prompt_version','prompt_variant','order_policy'].map(k=>`<div class=\"auditRow\"><strong>${{titleCase(k)}}</strong><span class=\"muted\">${{esc(method[k])}}</span></div>`).join('')}}<div class=\"warning\">Synthetic respondent simulation. Not observed consumer behavior. Decision-grade claims require external calibration.</div></article><article class=\"card\"><h3>Audit cards</h3>${{(data.quality?.cards||[]).map(c=>`<div class=\"auditRow\"><strong>${{esc(c.name)}}</strong><span class=\"muted\">${{esc(c.status)}}</span></div>`).join('')}}</article><article class=\"card\"><h3>Artifacts</h3>${{(data.artifacts||[]).slice(0,12).map(a=>`<div class=\"artifactRow\"><strong>${{esc(a.name)}}</strong><span class=\"muted\">${{esc(a.path)}}</span></div>`).join('')}}</article></div></section>
  <section class=\"section\"><p class=\"eyebrow\">06 · Deep case layer</p><h2>Compact case cards</h2><p>These examples explain the simulation; they do not estimate market share.</p><div class=\"four\">${{(data.sample_layers?.deep_case_cards||[]).slice(0,12).map(c=>`<article class=\"card case\"><p class=\"eyebrow\">${{esc(c.persona_id)}}</p><h3>${{esc(c.archetype_label)}}</h3><p class=\"muted\">${{Object.entries(c.hard||{{}}).map(([k,v])=>`${{titleCase(k)}}: ${{titleCase(v)}}`).join(' · ')}}</p><div class=\"choice\">${{choiceLabels[c.choice]||titleCase(c.choice)}}</div><p><strong>Drivers:</strong> ${{esc((c.main_drivers||[]).join(' / ')||'—')}}</p><p><strong>Barriers:</strong> ${{esc((c.main_barriers||[]).join(' / ')||'—')}}</p></article>`).join('')}}</div></section>
  <footer><span>Generated at {html.escape(generated_at)}</span><span>Source: {source}</span><span>Manifest: {manifest}</span></footer>
`;
</script>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--dashboard-data", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    data, manifest_path, source_path = choose_dashboard_data(args.manifest, args.dashboard_data)
    write_text(args.output, render_html(data, source_path=source_path, manifest_path=manifest_path))
    print(json.dumps({"output": str(args.output), "dashboard_data": str(source_path), "html_generator_version": HTML_GENERATOR_VERSION}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
