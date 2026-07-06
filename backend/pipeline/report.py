"""
report.py — self-contained HTML report of a trained model (shareable dossier).

Assembles what a CERT / SOC analyst would hand to a colleague or attach to a
ticket: what the model does, how good it is, its recommended operating point, a
data-driven assessment (strengths / cautions), and the diagnostic figures — all
in ONE self-contained HTML file (plots are already base64 data-URIs, so no
external assets, no network, no new dependency). Everything comes from recorded
session state via ``scoring.model_card`` and the stored stage plots — nothing is
invented.
"""

from __future__ import annotations

import html

from . import scoring

_CSS = """
body{font-family:system-ui,Segoe UI,Arial,sans-serif;max-width:900px;margin:2rem auto;
padding:0 1rem;color:#1a1a2e;background:#fff;line-height:1.5}
h1{font-size:1.5rem;margin:0 0 .2rem}h2{font-size:1.05rem;margin:1.6rem 0 .5rem;
border-bottom:2px solid #e94560;padding-bottom:.2rem}
.sub{color:#555;font-size:.85rem;margin-bottom:1rem}
.headline{font-size:1.05rem;background:#f5f6fa;border-left:4px solid #e94560;padding:.6rem .9rem;border-radius:4px}
table{border-collapse:collapse;width:100%;font-size:.85rem;margin:.4rem 0}
th,td{border:1px solid #e2e2ea;padding:.35rem .6rem;text-align:left}
th{background:#0f3460;color:#fff}
.verdict{display:inline-block;font-weight:700;padding:.15rem .6rem;border-radius:5px}
.v-ok{background:#dff5ec;color:#0a7a54}.v-warn{background:#fdf1dd;color:#9a6b16}.v-bad{background:#fde3e7;color:#b3243b}
ul{margin:.2rem 0;padding-left:1.2rem}.caution li{color:#9a6b16}
.figs{display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin-top:.6rem}
.figs figure{margin:0}.figs img{max-width:100%;border:1px solid #eee;border-radius:6px}
figcaption{font-size:.75rem;color:#555;margin-top:.2rem}
footer{margin-top:2rem;font-size:.72rem;color:#888;border-top:1px solid #eee;padding-top:.6rem}
"""

_VERDICT_CLASS = {"Déployable": "v-ok", "À utiliser avec prudence": "v-warn", "Fragile": "v-bad"}


def _esc(v) -> str:
    return html.escape(str(v))


def _kv_table(d: dict) -> str:
    if not d:
        return "<p>—</p>"
    rows = "".join(f"<tr><td>{_esc(k)}</td><td>{_esc(v)}</td></tr>" for k, v in d.items())
    return f"<table>{rows}</table>"


def _list(items) -> str:
    if not items:
        return ""
    return "<ul>" + "".join(f"<li>{_esc(x)}</li>" for x in items) + "</ul>"


def _figures(plots) -> str:
    figs = []
    for p in (plots or []):
        img = p.get("img") if isinstance(p, dict) else p
        cap = p.get("caption", "") if isinstance(p, dict) else ""
        if not img:
            continue
        figs.append(f'<figure><img src="{img}" alt="{_esc(cap)}"/>'
                    + (f"<figcaption>{_esc(cap)}</figcaption>" if cap else "") + "</figure>")
    return f'<div class="figs">{"".join(figs)}</div>' if figs else "<p>—</p>"


def _operating_point_html(op) -> str:
    if not op:
        return ""
    def pct(v):
        return "—" if v is None else f"{round(float(v) * 100)}%"
    return ("<h2>Point de fonctionnement recommandé</h2>"
            f"<p>Seuil <strong>{_esc(op.get('threshold'))}</strong> — détection "
            f"{pct(op.get('recall'))}, précision {pct(op.get('precision'))}, "
            f"{pct(op.get('alert_rate'))} d'alertes.</p>")


def _assessment_html(a) -> str:
    if not a:
        return ""
    vcls = _VERDICT_CLASS.get(a.get("verdict"), "v-warn")
    out = ["<h2>Évaluation</h2>",
           f'<p>Verdict : <span class="verdict {vcls}">{_esc(a.get("verdict"))}</span></p>']
    if a.get("strengths"):
        out.append("<p><strong>Points forts</strong></p>" + _list(a["strengths"]))
    if a.get("cautions"):
        out.append('<p><strong>À surveiller</strong></p><div class="caution">'
                   + _list(a["cautions"]) + "</div>")
    return "".join(out)


def build_html_report(session) -> str:
    """Assemble the full self-contained HTML report for a trained session."""
    card = scoring.model_card(session)
    ev = session.get_run("evaluate")
    ex = session.get_run("explain")
    ev_plots = ev.result.get("plots", []) if ev else []
    ex_plots = ex.result.get("plots", []) if ex else []
    tags = " · ".join(str(x) for x in [
        card.get("algorithm"),
        f"{card.get('n_rows')} lignes",
        f"{card.get('n_features')} variables",
    ] if x)

    body = [
        f"<h1>Rapport de modèle — {_esc(card.get('target') or 'cible')}</h1>",
        f'<div class="sub">{_esc(tags)}'
        + (f" · {_esc(card.get('created_at'))}" if card.get("created_at") else "") + "</div>",
        f'<p class="headline">{_esc(card.get("present"))}</p>',
        "<h2>Performance</h2>", _kv_table(card.get("metrics") or {}),
        _operating_point_html(card.get("operating_point")),
        _assessment_html(card.get("assessment")),
        "<h2>Variables clés</h2><p>" + _esc(", ".join(card.get("top_features") or []) or "—") + "</p>",
        "<h2>Diagnostics (Évaluation)</h2>", _figures(ev_plots),
    ]
    if ex_plots:
        body += ["<h2>Explicabilité</h2>", _figures(ex_plots)]
    body.append("<footer>Rapport généré par ML Automator — données issues de l'état de session "
                "(aucune valeur inventée). À valider par un expert avant tout usage opérationnel.</footer>")

    return ("<!doctype html><html lang=\"fr\"><head><meta charset=\"utf-8\">"
            f"<title>Rapport modèle — {_esc(card.get('target') or '')}</title>"
            f"<style>{_CSS}</style></head><body>{''.join(body)}</body></html>")
