"""
registry.py — Ordered registry of pipeline stages.

The canonical construction order is the user-requested data-prep taxonomy
followed by modelling, fine-tuning, evaluation and explainability:

    Nettoyage -> Transformation -> Integration -> Separation
    -> Model -> Fine-tuning -> Evaluation -> Explicability
"""

from .stages import clean, transform, integrate, separate, model, tune, evaluate, explain

STAGES = {
    clean.STAGE_ID: clean,
    transform.STAGE_ID: transform,
    integrate.STAGE_ID: integrate,
    separate.STAGE_ID: separate,
    model.STAGE_ID: model,
    tune.STAGE_ID: tune,
    evaluate.STAGE_ID: evaluate,
    explain.STAGE_ID: explain,
}

STAGE_IDS = ["clean", "transform", "integrate", "separate", "model", "tune", "evaluate", "explain"]
DATA_STAGE_IDS = ["clean", "transform", "integrate", "separate"]
MODEL_STAGE_IDS = ["model", "tune", "evaluate", "explain"]


def get_stage(stage_id):
    return STAGES.get(stage_id)


def stage_meta(stage_id) -> dict:
    m = STAGES[stage_id]
    return {
        "stage_id": m.STAGE_ID,
        "title": m.TITLE,
        "objective": m.OBJECTIVE,
        "kind": "data" if stage_id in DATA_STAGE_IDS else "model",
        "index": STAGE_IDS.index(stage_id) + 1,
    }


def all_stage_meta() -> list:
    return [stage_meta(sid) for sid in STAGE_IDS]
