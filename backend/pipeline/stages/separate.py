"""
separate.py — Stage 4 : SEPARATION.

Responsibility: separate features from target, then split into train / test
(optionally a validation carve-out), with stratification for classification.
Runs a leakage check (a feature almost perfectly correlated with the target is
a red flag) and stores the split arrays as session artefacts consumed by the
Model and Evaluation stages.

For clustering (no target) there is no train/test split — the full feature
matrix is forwarded, and the stage says so explicitly.
"""

import numpy as np
import pandas as pd

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

from .. import diagnostics as dg
from ..plotting import style_plot, fig_to_base64, message_plot
from ..context import CLASSIFICATION, REGRESSION
from .base import select, toggle, rng, number

STAGE_ID = "separate"
TITLE = "Séparation"
OBJECTIVE = "Séparer X/cible puis train/test, vérifier l'équilibre des classes et l'absence de fuite."


def default_config(df, ctx):
    return {
        "target_col": ctx.target_col or "",
        "test_size": 0.25,
        "validation_size": 0.0,
        "stratify": ctx.problem_type == CLASSIFICATION,
        "shuffle": True,
        "random_state": 42,
    }


def config_schema(df, ctx):
    cols = [(c, c) for c in df.columns]
    return [
        select("target_col", "Colonne cible", cols or [("", "—")], ctx.target_col or "",
               "Variable à prédire (vide = non supervisé / clustering)."),
        rng("test_size", "Taille du test", 0.1, 0.5, 0.05, 0.25, "Part des données réservée au test."),
        rng("validation_size", "Taille validation (sur train)", 0.0, 0.4, 0.05, 0.0,
            "Découpe optionnelle d'un jeu de validation à partir du train."),
        toggle("stratify", "Stratifier (classification)", ctx.problem_type == CLASSIFICATION,
               "Conserve la proportion des classes dans chaque jeu."),
        toggle("shuffle", "Mélanger", True, "Mélange les lignes avant le découpage."),
        number("random_state", "Graine aléatoire", 42, 0, 9999, "Reproductibilité du découpage."),
    ]


def diagnose(df, ctx):
    target = ctx.target_col
    plots = []
    leakage = _leakage_candidates(df, target, ctx)
    balance = _target_distribution(df, target, ctx)
    if target and target in df.columns:
        plots.append(_target_plot(df, target, ctx))
    else:
        plots.append(message_plot("Non supervisé : pas de cible, pas de séparation train/test."))
    return {
        "diagnostics": {
            "target_col": target,
            "problem_type": ctx.problem_type,
            "target_distribution": balance,
            "leakage_candidates": leakage,
            "n_features": len([c for c in df.columns if c != target]),
        },
        "plots": plots,
    }


def run(df, config, ctx):
    cfg = {**default_config(df, ctx), **(config or {})}
    df = df.copy()
    log, warnings = [], []
    target = cfg.get("target_col") or ctx.target_col

    # Allow the expert to override the detected target / type.
    if target and target in df.columns and not ctx.supervised:
        ctx.problem_type = CLASSIFICATION if df[target].nunique(dropna=True) <= 10 else REGRESSION
        ctx.target_col = target

    # ── Clustering / unsupervised : no split ───────────────────────────
    if not target or target not in df.columns:
        num, _ = dg.feature_columns(df, None)
        X_full = df[num].fillna(0)
        artifacts = {"mode": "unsupervised", "X_full": X_full, "feature_names": num, "target_col": None}
        result = {
            "report": {"Mode": "Non supervisé (clustering)", "Variables": len(num),
                       "Observations": int(len(df))},
            "diagnostics": {"split": "aucune (matrice complète)", "n_features": len(num)},
            "log": ["Non supervisé : matrice complète transmise au clustering."],
            "warnings": [], "plots": [message_plot("Clustering : aucune séparation train/test.")],
        }
        return df, result, artifacts

    # ── Supervised : X / y separation ──────────────────────────────────
    df = df[df[target].notna()]
    y_raw = df[target]
    X = df.drop(columns=[target])
    # Keep only numeric features for modelling (transform/integrate made them numeric).
    num_cols = X.select_dtypes(include=[np.number]).columns.tolist()
    X = X[num_cols].fillna(0)

    label_encoder = None
    if ctx.problem_type == CLASSIFICATION and not pd.api.types.is_numeric_dtype(y_raw):
        label_encoder = LabelEncoder()
        y = label_encoder.fit_transform(y_raw.astype(str))
    else:
        y = y_raw.to_numpy()

    # Leakage check before splitting.
    leakage = _leakage_candidates(df, target, ctx)
    if leakage:
        warnings.append("Fuite possible — variable(s) quasi-identique(s) à la cible : "
                        + ", ".join(d["column"] for d in leakage) + ".")
    warnings.append("Note : mises à l'échelle/encodages ont été ajustés sur l'ensemble des données. "
                    "Pour la production, préférez un Pipeline ajusté sur le train seul.")

    test_size = float(cfg["test_size"])
    rs = int(cfg["random_state"])
    stratify_arr = y if (cfg["stratify"] and ctx.problem_type == CLASSIFICATION and _stratifiable(y)) else None

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=rs, shuffle=bool(cfg["shuffle"]), stratify=stratify_arr,
    )

    artifacts = {
        "mode": "supervised",
        "X_train": X_train, "X_test": X_test, "y_train": y_train, "y_test": y_test,
        "feature_names": num_cols, "target_col": target,
        "label_encoder": label_encoder, "problem_type": ctx.problem_type,
    }
    log.append(f"Séparation X/cible : {len(num_cols)} variables, cible « {target} ».")
    log.append(f"Train/Test : {len(X_train)} / {len(X_test)} (test={test_size}).")

    # Optional validation carve-out from the training set.
    val_size = float(cfg["validation_size"])
    if val_size > 0:
        strat2 = y_train if stratify_arr is not None else None
        X_train, X_val, y_train, y_val = train_test_split(
            X_train, y_train, test_size=val_size, random_state=rs, stratify=strat2,
        )
        artifacts.update({"X_train": X_train, "y_train": y_train, "X_val": X_val, "y_val": y_val})
        log.append(f"Validation : {len(X_val)} lignes extraites du train.")

    plots = [_split_balance_plot(y_train, y_test, ctx, label_encoder)]
    result = {
        "report": {
            "Cible": target,
            "Variables": len(num_cols),
            "Train": int(len(X_train)),
            "Test": int(len(X_test)),
            "Stratifié": "oui" if stratify_arr is not None else "non",
            "Fuite détectée": "oui" if leakage else "non",
        },
        "diagnostics": {
            "n_features": len(num_cols),
            "train_size": int(len(X_train)),
            "test_size": int(len(X_test)),
            "leakage_candidates": leakage,
            "stratified": stratify_arr is not None,
        },
        "log": log, "warnings": warnings, "plots": plots,
    }
    return df, result, artifacts


# ── helpers ───────────────────────────────────────────────────────────────
def _stratifiable(y) -> bool:
    vals, cnts = np.unique(y, return_counts=True)
    return len(vals) >= 2 and cnts.min() >= 2


def _leakage_candidates(df, target, ctx):
    if not target or target not in df.columns:
        return []
    y = df[target]
    if not pd.api.types.is_numeric_dtype(y):
        try:
            y = pd.Series(LabelEncoder().fit_transform(y.astype(str)), index=df.index)
        except Exception:
            return []
    num, _ = dg.feature_columns(df, target)
    out = []
    for c in num:
        try:
            r = abs(float(df[c].corr(y)))
        except Exception:
            continue
        if np.isfinite(r) and r > 0.999:
            out.append({"column": str(c), "corr": round(r, 4)})
    return out


def _target_distribution(df, target, ctx):
    if not target or target not in df.columns:
        return None
    if ctx.problem_type == CLASSIFICATION:
        vc = df[target].value_counts()
        return {str(k): int(v) for k, v in vc.items()}
    s = df[target].dropna()
    return {"min": round(float(s.min()), 2), "max": round(float(s.max()), 2),
            "mean": round(float(s.mean()), 2), "std": round(float(s.std()), 2)}


def _target_plot(df, target, ctx):
    import matplotlib.pyplot as plt
    style_plot()
    fig, ax = plt.subplots(figsize=(6, 3.5))
    if ctx.problem_type == CLASSIFICATION:
        vc = df[target].value_counts()
        ax.bar([str(i) for i in vc.index], vc.values, color="#e94560", edgecolor="#eee")
        ax.set_title(f"Classes de {target}")
    else:
        ax.hist(df[target].dropna(), bins=30, color="#e94560", edgecolor="#0f3460")
        ax.set_title(f"Distribution de {target}")
    fig.tight_layout()
    return fig_to_base64(fig)


def _split_balance_plot(y_train, y_test, ctx, label_encoder):
    import matplotlib.pyplot as plt
    style_plot()
    fig, ax = plt.subplots(figsize=(6.5, 3.6))
    if ctx.problem_type == CLASSIFICATION:
        classes = np.unique(np.concatenate([y_train, y_test]))
        names = (label_encoder.inverse_transform(classes.astype(int))
                 if label_encoder is not None else [str(c) for c in classes])
        tr = [int((y_train == c).sum()) for c in classes]
        te = [int((y_test == c).sum()) for c in classes]
        x = np.arange(len(classes))
        ax.bar(x - 0.2, tr, 0.4, label="Train", color="#0f3460", edgecolor="#eee")
        ax.bar(x + 0.2, te, 0.4, label="Test", color="#e94560", edgecolor="#eee")
        ax.set_xticks(x)
        ax.set_xticklabels([str(n) for n in names], rotation=0)
        ax.set_title("Équilibre des classes par jeu")
        ax.legend()
    else:
        ax.hist(y_train, bins=25, alpha=0.6, label="Train", color="#0f3460")
        ax.hist(y_test, bins=25, alpha=0.6, label="Test", color="#e94560")
        ax.set_title("Distribution de la cible par jeu")
        ax.legend()
    fig.tight_layout()
    return fig_to_base64(fig)
