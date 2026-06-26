"""
agent_prompts.py — Prompt engineering for the per-stage refinement agent.

Applies several established techniques so the agent returns grounded, minimal,
professional JSON regardless of model size:
- Role prompting (senior data scientist).
- An explicit step-by-step METHOD (chain-of-thought, kept internal).
- Delimited sections (RÔLE / MÉTHODE / SORTIE / RÈGLES) for clarity.
- A strict output contract with an inline shape example.
- One representative FEW-SHOT example per stage (real diagnostics -> ideal JSON),
  injected as a user/assistant turn before the actual request.

Cf. prompt-engineering best practices: instructions first, delimiters, explicit
output format, few-shot examples, positive framing, minimal-change bias.
"""

import json

import prompt_store

DEFAULT_SYSTEM_PROMPT = (
    "# RÔLE\n"
    "Tu es un data scientist senior. Tu affines la configuration d'UNE étape d'un pipeline de "
    "machine learning, à partir de diagnostics chiffrés réels du jeu de données. Tu es rigoureux, "
    "sobre, et tu ne sur-ingénieres jamais.\n\n"
    "# MÉTHODE (raisonne ainsi, en interne, sans l'afficher)\n"
    "1. Lis les DIAGNOSTICS et repère les 1 à 3 problèmes RÉELS les plus impactants pour le modèle.\n"
    "2. Pour chaque problème, choisis dans le SCHÉMA le réglage qui le corrige (clé + valeur autorisée).\n"
    "3. Écarte les artefacts : une colonne identifiant (id, *_id, index, 'Unnamed') n'est PAS une "
    "variable ; une métrique non nulle n'impose pas d'action si l'impact est négligeable.\n"
    "4. Vise le changement MINIMAL utile. Si la configuration actuelle convient déjà, propose peu ou rien.\n\n"
    "# SORTIE\n"
    "Réponds par UN SEUL objet JSON, sans aucun texte ni balise autour, suivant EXACTEMENT ce format :\n"
    '{"summary": "phrase courte", "rationale": ["raison appuyée sur un chiffre"], '
    '"suggested_config": {"cle_du_schema": valeur_autorisee}, "risk": "phrase courte", "confidence": 0.7}\n\n'
    "# RÈGLES\n"
    "- suggested_config n'emploie QUE des clés présentes dans le schéma et des valeurs autorisées. "
    "Jamais de clé inventée.\n"
    "- Chaque entrée de rationale cite un CHIFFRE précis des diagnostics et l'interprète. N'invente "
    "aucun chiffre ; ne cite jamais une colonne identifiant.\n"
    "- summary, rationale et risk en FRANÇAIS, courts, précis, professionnels.\n"
    "- confidence ∈ [0,1] reflète ta certitude réelle ; en cas de doute, propose moins et baisse confidence.\n"
    "- 'exclude_column' exclut des LIGNES selon une vraie variable aux valeurs extrêmes ; jamais pour une "
    "colonne très incomplète (gérée par le seuil de colonnes) ni pour un identifiant.\n"
    "- Suis le style des EXEMPLES fournis : concis, chiffré, minimal."
)


# One representative few-shot example per stage : (diagnostics_in, recommendation_out).
# Diagnostics are trimmed to what justifies the recommendation.
DEFAULT_STAGE_EXAMPLES = {
    "clean": (
        {"overview": {"missing_pct": 6.6, "duplicated_rows": 0},
         "typologie": [{"type": "Catégorielle ordinale", "count": 10}],
         "missing_by_column": [{"column": "MasVnrArea", "pct": 0.5}],
         "outliers_iqr": [{"column": "GrLivArea", "outliers": 31, "pct": 5.1}]},
        {"summary": "Imputer les manquants, normaliser les ordinales, borner les aberrants",
         "rationale": ["6.6% de valeurs manquantes : imputation (médiane / 'None' pour l'absence)",
                       "10 variables ordinales : normaliser sur l'échelle Po=1…Ex=5",
                       "GrLivArea : 5.1% de valeurs hors bornes IQR, à borner"],
         "suggested_config": {"impute_num": "median", "impute_cat": "constant",
                              "normalize_ordinals": True, "outlier_method": "iqr_clip"},
         "risk": "Faible : le choix des colonnes reste à l'expert (table dédiée)", "confidence": 0.8}),

    "transform": (
        {"typologie": [{"type": "Catégorielle nominale", "count": 33},
                       {"type": "Catégorielle ordinale", "count": 10}],
         "ordinales_detectees": ["ExterQual", "KitchenQual"],
         "skewness": [{"column": "LotArea", "abs_skew": 12.2}]},
        {"summary": "Redresser l'asymétrie, encoder les nominales en One-Hot, standardiser",
         "rationale": ["LotArea très asymétrique (|skew|=12.2) : redressement",
                       "33 variables nominales : One-Hot pour éviter un faux ordre",
                       "Échelles hétérogènes : StandardScaler"],
         "suggested_config": {"skew_correction": True, "skew_threshold": 1.0,
                              "nominal_encoding": "onehot", "scaler": "standard"},
         "risk": "Faible", "confidence": 0.8}),

    "integrate": (
        {"n_features": 32,
         "high_correlation_pairs": [{"a": "radius_mean", "b": "perimeter_mean", "corr": 0.998}],
         "target_correlation": [{"column": "concave points_worst", "abs_corr": 0.79}]},
        {"summary": "Retirer la redondance entre variables très corrélées",
         "rationale": ["radius_mean et perimeter_mean corrélées à 0.998 : redondance, en retirer une",
                       "On garde celle la plus liée à la cible, on retire l'autre"],
         "suggested_config": {"dropped_features": ["perimeter_mean"], "pca": False},
         "risk": "Faible : on conserve la variable la plus liée à la cible", "confidence": 0.78}),

    "separate": (
        {"problem_type": "classification",
         "target_distribution": {"M": 212, "B": 357},
         "leakage_candidates": [], "n_features": 30},
        {"summary": "Découpage train/test stratifié",
         "rationale": ["Classes déséquilibrées (212 vs 357) : stratifier pour préserver les proportions",
                       "Aucune fuite détectée"],
         "suggested_config": {"stratify": True, "test_size": 0.25},
         "risk": "Faible", "confidence": 0.85}),

    "model": (
        {"ready": True, "mode": "supervised", "train_size": 1095, "n_features": 60},
        {"summary": "Random Forest comme modèle robuste de référence",
         "rationale": ["1095 observations et 60 variables : une forêt aléatoire (200 arbres) est robuste"],
         "suggested_config": {"algorithm": "RandomForest", "n_estimators": 200},
         "risk": "Faible : baseline solide à comparer ensuite", "confidence": 0.75}),

    "tune": (
        {"ready": True, "baseline_algorithm": "RandomForest"},
        {"summary": "Optimiser le Gradient Boosting par validation croisée",
         "rationale": ["Baseline en place : rechercher learning_rate × n_estimators en 3 plis"],
         "suggested_config": {"algorithm": "GradientBoosting", "cv": 3},
         "risk": "Coût de calcul accru ; gain non garanti sur le test", "confidence": 0.6}),

    "evaluate": (
        {"ready": True},
        {"summary": "Aucun paramètre à régler ; lire les métriques de test",
         "rationale": ["Comparer R²/RMSE (régression) ou Accuracy/F1 + matrice de confusion (classif.) au besoin métier"],
         "suggested_config": {}, "risk": "—", "confidence": 0.6}),

    "explain": (
        {"ready": True, "shap_tree_supported": True},
        {"summary": "Expliquer une prédiction représentative",
         "rationale": ["Modèle à base d'arbres : SHAP disponible ; décomposer l'observation d'indice 0"],
         "suggested_config": {"sample_index": 0},
         "risk": "Faible", "confidence": 0.7}),
}


def _example_messages(stage_id: str, problem_type: str) -> list:
    base = DEFAULT_STAGE_EXAMPLES.get(stage_id)
    if not base:
        return []
    # Resolve a possible UI override; few-shots are stored as {"input", "output"}.
    ex = prompt_store.STORE.resolve("fewshot_" + stage_id, {"input": base[0], "output": base[1]})
    try:
        diag_in, reco_out = ex["input"], ex["output"]
    except (KeyError, TypeError):
        diag_in, reco_out = base
    user = ("EXEMPLE — entrée :\n"
            + json.dumps({"problem_type": problem_type, "diagnostics": diag_in}, ensure_ascii=False))
    assistant = json.dumps(reco_out, ensure_ascii=False)
    return [{"role": "user", "content": user}, {"role": "assistant", "content": assistant}]


DEFAULT_INTERPRET_SYSTEM = (
    "Tu es un data scientist senior. À partir des RÉSULTATS chiffrés d'une étape de machine "
    "learning, rédige une INTERPRÉTATION honnête en français : ce que disent les chiffres, ce qui "
    "est bon ou préoccupant, et la conclusion pratique pour la suite.\n\n"
    "Réponds par UN SEUL objet JSON, sans texte autour :\n"
    '{"interpretation": ["point appuyé sur un chiffre", "..."], "verdict": "phrase de synthèse", '
    '"confidence": 0.7}\n\n'
    "RÈGLES :\n"
    "- 2 à 5 points ; chaque point cite un CHIFFRE réel des résultats et l'interprète. N'invente rien.\n"
    "- Français concis, professionnel, factuel. Pas de jargon inutile.\n"
    "- Signale clairement un problème (surapprentissage, métrique faible, fuite) si les chiffres le montrent.\n"
    "- verdict = une phrase de synthèse actionnable ; confidence ∈ [0,1]."
)


def build_interpret_messages(stage_title: str, problem_type: str, payload: dict, journal: str = "") -> list:
    parts = ["Étape : " + str(stage_title) + " | Type de problème : " + str(problem_type)]
    if journal:
        parts.append(journal)
    parts.append("RÉSULTATS à interpréter (JSON) :\n" + json.dumps(payload, ensure_ascii=False))
    system = prompt_store.STORE.resolve("interpret_system", DEFAULT_INTERPRET_SYSTEM)
    return [{"role": "system", "content": system}, {"role": "user", "content": "\n\n".join(parts)}]


DEFAULT_ASSIST_SYSTEM = (
    "Tu es un assistant d'analyse de données spécialisé, en binôme avec un analyste. Il te demande de "
    "l'aider à COMPRENDRE un élément précis d'une étape (un tableau, un graphique, un diagnostic chiffré). "
    "Explique en français, pédagogiquement et honnêtement, en t'appuyant sur les CHIFFRES fournis.\n\n"
    "Réponds par UN SEUL objet JSON, sans texte autour :\n"
    '{"explanation": ["point clair appuyé sur une donnée réelle", "..."], '
    '"takeaway": "ce qu\'il faut en retenir / décider", '
    '"suggested_config": {}, "confidence": 0.7}\n\n'
    "RÈGLES :\n"
    "- 2 à 4 points ; chaque point s'appuie sur une donnée réelle du contexte. N'invente AUCUN chiffre.\n"
    "- Niveau NOVICE : vulgarise, explique les termes, donne le « pourquoi ». "
    "Niveau EXPERT : concis et technique, va à l'essentiel.\n"
    "- takeaway = une phrase actionnable pour la suite de l'analyse.\n"
    "- suggested_config : c'est le PONT VERS L'ACTION. Si ton explication recommande une action "
    "réalisable via le schéma fourni, tu DOIS la refléter ici, sinon l'analyste ne peut rien faire "
    "de ton conseil. Utilise UNIQUEMENT des clés/valeurs valides du schéma.\n"
    "  Exemples : si tu conseilles de retirer les colonnes PoolQC et Alley et que le schéma a un "
    "contrôle column_table (ex. 'dropped_columns'), renvoie {\"dropped_columns\": [\"PoolQC\", \"Alley\"]} "
    "(la LISTE des colonnes à retirer). Si tu conseilles l'imputation par la médiane et que le schéma "
    "a 'impute_num', renvoie {\"impute_num\": \"median\"}.\n"
    "  Si AUCUNE action de config n'est pertinente (simple lecture d'un graphe sans décision), "
    "renvoie un objet vide {}.\n"
    "- Tiens compte du JOURNAL (ce qui a déjà été dit) pour rester cohérent et éviter les répétitions."
)


def build_assist_messages(stage_title: str, problem_type: str, topic: str, focus: dict,
                          journal: str = "", level: str = "novice",
                          compact_schema: list = None, current_config: dict = None) -> list:
    parts = [
        "Étape : " + str(stage_title) + " | Type : " + str(problem_type) + " | Niveau analyste : " + str(level),
        "Élément à expliquer : " + str(topic),
    ]
    if journal:
        parts.append(journal)
    parts.append("DONNÉES de l'élément (JSON) :\n" + json.dumps(focus, ensure_ascii=False))
    if compact_schema is not None:
        parts.append("SCHÉMA de configuration applicable + CONFIG ACTUELLE (pour suggested_config) :\n"
                     + json.dumps({"config_schema": compact_schema, "current_config": current_config or {}},
                                  ensure_ascii=False))
    system = prompt_store.STORE.resolve("assist_system", DEFAULT_ASSIST_SYSTEM)
    return [{"role": "system", "content": system}, {"role": "user", "content": "\n\n".join(parts)}]


def build_messages(stage_meta: dict, problem_type: str, compact_schema: list,
                   current_config: dict, diagnostics: dict, journal: str = "") -> list:
    """Assemble the chat messages: system + one few-shot turn + the real request."""
    user_content = (
        "Étape à affiner : " + str(stage_meta["title"]) + " — " + str(stage_meta["objective"]) + "\n"
        "Type de problème : " + str(problem_type) + "\n\n"
        + (journal + "\n\n" if journal else "")
        + "SCHÉMA de configuration, CONFIG ACTUELLE et DIAGNOSTICS (JSON) :\n"
        + json.dumps({
            "config_schema": compact_schema,
            "current_config": current_config,
            "diagnostics": diagnostics,
        }, ensure_ascii=False)
    )
    system = prompt_store.STORE.resolve("recommend_system", DEFAULT_SYSTEM_PROMPT)
    return (
        [{"role": "system", "content": system}]
        + _example_messages(stage_meta.get("stage_id", ""), problem_type)
        + [{"role": "user", "content": user_content}]
    )


# ── Prompt catalog (for the "Prompts IA" panel) ──────────────────────────
# Each entry advertises where the prompt is used in the UI ("localisation") so
# the panel can point the analyst to the exact spot. ``loc`` matches the
# ``data-prompt-loc`` attribute carried by the triggering element in the front.

_STAGE_LABELS = {
    "clean": "Nettoyage", "transform": "Transformation", "integrate": "Intégration",
    "separate": "Séparation", "model": "Modèle", "tune": "Fine-tuning",
    "evaluate": "Évaluation", "explain": "Explicabilité",
}

_RECO_LOC = {
    "view": "Pipeline",
    "trigger": "Bouton « Demander à l'agent » dans le panneau d'étape",
    "endpoint": "POST /api/session/{id}/stage/{stage}/recommend",
    "component": "frontend/src/components/AgentRecommendation.jsx",
    "loc": "recommend",
}

# Static metadata for the three system prompts. Few-shot entries are appended
# programmatically below (one per stage).
_SYSTEM_ENTRIES = [
    {
        "id": "recommend_system", "kind": "text", "label": "Agent — instructions système",
        "description": "Rôle, méthode et contrat de sortie de l'agent qui propose l'affinage d'une étape.",
        "localisation": _RECO_LOC,
    },
    {
        "id": "interpret_system", "kind": "text", "label": "Interprétation — instructions système",
        "description": "Cadre la lecture chiffrée et honnête des résultats d'une étape exécutée.",
        "localisation": {
            "view": "Pipeline",
            "trigger": "Bouton « Interpréter » après l'exécution d'une étape",
            "endpoint": "POST /api/session/{id}/stage/{stage}/interpret",
            "component": "frontend/src/components/StagePanel.jsx",
            "loc": "interpret",
        },
    },
    {
        "id": "assist_system", "kind": "text", "label": "Assistant « IA » — instructions système",
        "description": "Explique un élément précis (tableau, graphe, diagnostic) et propose une action applicable.",
        "localisation": {
            "view": "Pipeline / Renforcement",
            "trigger": "Boutons « IA » sur les badges, les étapes et les graphiques",
            "endpoint": "POST /api/session/{id}/stage/{stage}/assist",
            "component": "frontend/src/components/AssistAnswer.jsx",
            "loc": "assist",
        },
    },
]


def get_default(prompt_id: str):
    """Default value (text or JSON) for a catalog prompt id, or ``None``."""
    if prompt_id == "recommend_system":
        return DEFAULT_SYSTEM_PROMPT
    if prompt_id == "interpret_system":
        return DEFAULT_INTERPRET_SYSTEM
    if prompt_id == "assist_system":
        return DEFAULT_ASSIST_SYSTEM
    if prompt_id.startswith("fewshot_"):
        base = DEFAULT_STAGE_EXAMPLES.get(prompt_id[len("fewshot_"):])
        return {"input": base[0], "output": base[1]} if base else None
    return None


def _entries() -> list:
    entries = [dict(e) for e in _SYSTEM_ENTRIES]
    for stage_id in DEFAULT_STAGE_EXAMPLES:
        label = _STAGE_LABELS.get(stage_id, stage_id)
        loc = dict(_RECO_LOC)
        loc["trigger"] = "Exemple few-shot injecté avant la recommandation de l'étape « " + label + " »"
        entries.append({
            "id": "fewshot_" + stage_id, "kind": "json",
            "label": "Few-shot — " + label,
            "description": "Exemple (diagnostics → recommandation idéale) guidant l'agent pour l'étape « " + label + " ».",
            "localisation": loc,
        })
    return entries


def catalog() -> list:
    """Full prompt catalog with default + current value and override flag, for the
    Prompts IA panel. ``value``/``default`` are strings (text) or JSON (few-shot)."""
    out = []
    for e in _entries():
        default = get_default(e["id"])
        out.append({
            **e,
            "default": default,
            "value": prompt_store.STORE.resolve(e["id"], default),
            "overridden": prompt_store.STORE.is_overridden(e["id"]),
        })
    return out


def is_valid_id(prompt_id: str) -> bool:
    return any(e["id"] == prompt_id for e in _entries())


def kind_of(prompt_id: str):
    return next((e["kind"] for e in _entries() if e["id"] == prompt_id), None)
