"""
predict.py — Turnkey scorer for an AEGIS-exported model bundle.

Usage:
    pip install -r requirements.txt
    python predict.py input.csv [output.csv]

``input.csv`` holds RAW rows (the ORIGINAL columns, same as the training data —
missing columns are completed with sensible defaults). The script writes an
enriched CSV with a ``prediction`` column (+ ``confidence`` for classification,
``anomaly_score`` for anomaly detection) and prints a distribution summary.

Programmatic use:
    from predict import load_session
    from aegis_pipeline import scoring
    enriched, summary = scoring.score_dataframe(load_session(), my_dataframe)

Predictions are byte-faithful to the AEGIS app: the bundle ships the project's
own transform code (aegis_pipeline/) and re-derives the exact preprocessing from
training_data.csv, as the server does.
"""

import json
import sys
from pathlib import Path

import joblib
import pandas as pd

import aegis_pipeline
from aegis_pipeline import preprocessing as _preprocessing
from aegis_pipeline import scoring
from aegis_pipeline import stages as _stages
from aegis_pipeline.stages import clean as _clean

# The preprocessors were pickled under the app's module paths
# ("pipeline.preprocessing", "pipeline.stages.clean"); alias them to the bundled
# package so joblib can unpickle.
sys.modules.setdefault("pipeline", aegis_pipeline)
sys.modules.setdefault("pipeline.preprocessing", _preprocessing)
sys.modules.setdefault("pipeline.stages", _stages)
sys.modules.setdefault("pipeline.stages.clean", _clean)

HERE = Path(__file__).resolve().parent
_META = json.loads((HERE / "config.json").read_text(encoding="utf-8"))
_BUNDLE = joblib.load(HERE / "model.joblib")
_RAW_DF = pd.read_csv(HERE / "training_data.csv")


class _Run:
    """Minimal stand-in for a recorded pipeline stage (config + artefacts)."""

    def __init__(self, config=None, artifacts=None):
        self.config = config or {}
        self.artifacts = artifacts or {}
        self.stale = False


class _Ctx:
    def __init__(self, meta):
        self.problem_type = meta["problem_type"]
        self.target_col = meta["target"]
        self.supervised = bool(meta["supervised"])


class _Session:
    """Reconstructs just enough of the training session for the serving layer."""

    def __init__(self):
        self.raw_df = _RAW_DF
        self.ctx = _Ctx(_META)
        self.created_at = _META.get("created_at")
        self._runs = {
            "clean": _Run(config=_META.get("clean_cfg")),
            "transform": _Run(config=_META.get("transform_cfg")),
            "integrate": _Run(config=_META.get("integrate_cfg")),
            "separate": _Run(artifacts={
                "feature_names": _META.get("feature_names"),
                "label_encoder": _BUNDLE.get("label_encoder"),
                "X_full": _BUNDLE.get("X_full"),
                "preprocessor": _BUNDLE.get("preprocessor"),
                "clean_preprocessor": _BUNDLE.get("clean_preprocessor"),
            }),
            "model": _Run(artifacts={
                "model": _BUNDLE["model"],
                "labels": _BUNDLE.get("labels"),
            }),
        }

    def get_run(self, stage_id):
        return self._runs.get(stage_id)

    def current_model(self):
        return _BUNDLE["model"], "exported"


def load_session():
    """The reconstructed session, for programmatic use with aegis_pipeline.scoring."""
    return _Session()


def main():
    if len(sys.argv) < 2:
        print("Usage: python predict.py <input.csv> [output.csv]")
        sys.exit(1)
    inp = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else inp.with_name(inp.stem + "_scored.csv")
    df = pd.read_csv(inp)
    enriched, summary = scoring.score_dataframe(load_session(), df)
    enriched.to_csv(out, index=False)
    print("Scored " + str(len(enriched)) + " row(s) -> " + str(out))
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
