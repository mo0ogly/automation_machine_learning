"""
routes_report.py — downloadable self-contained HTML model report.

A dedicated router (mounted in app.py) so the report concern stays isolated and
app.py stays within the file-size budget. Returns the full HTML dossier
(model card + metrics + operating point + assessment + figures) as a download.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from pipeline import SESSIONS
from pipeline import report as report_builder

router = APIRouter(prefix="/api/session", tags=["report"])


@router.get("/{session_id}/report")
def model_report(session_id: str):
    """Self-contained HTML report of the trained model (Content-Disposition: attachment)."""
    session = SESSIONS.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session inconnue.")
    if session.get_run("separate") is None or session.get_run("model") is None:
        raise HTTPException(status_code=409, detail="Entraînez et évaluez le modèle d'abord.")
    try:
        html = report_builder.build_html_report(session)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Rapport indisponible ({type(e).__name__}).")
    name = (getattr(session, "filename", "modele") or "modele").rsplit(".", 1)[0]
    return Response(content=html, media_type="text/html; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="rapport_{name}.html"'})
