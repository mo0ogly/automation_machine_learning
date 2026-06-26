"""
explanations.py — Pedagogical narrative per stage (the "logique de construction
du dataset").

Each stage carries a short explanation, adapted to the learning track:
- SUPERVISED (regression / classification): a known target Y, train/test split,
  evaluation against ground truth.
- UNSUPERVISED (clustering): no target, no split, structure discovery + business
  interpretation of the clusters.

These texts are surfaced verbatim in the UI so the expert understands *why* each
stage shapes the dataset the way it does — not just *what* it does.
"""

from .context import REGRESSION, CLASSIFICATION


def for_stage(stage_id: str, ctx) -> dict:
    fn = _MAP.get(stage_id)
    base = fn(ctx) if fn else {"why": "", "dataset_logic": "", "supervision": ""}
    base["track"] = "supervised" if ctx.supervised else "unsupervised"
    base["track_label"] = (
        "Apprentissage supervisé" if ctx.supervised else "Apprentissage non supervisé"
    )
    return base


def _clean(ctx):
    return {
        "why": "Un modèle ne vaut jamais mieux que ses données. Avant toute construction, "
               "on fiabilise le jeu : valeurs manquantes, doublons et valeurs aberrantes "
               "fausseraient l'apprentissage.",
        "dataset_logic": "On raisonne d'abord par type de variable — quantitative continue "
                         "(surface, prix), quantitative discrète (nombre de pièces), catégorielle "
                         "nominale (sans ordre, ex. quartier) ou ordinale (avec ordre, ex. note de "
                         "qualité). Le traitement en dépend : une numérique s'impute par la médiane, "
                         "une catégorielle par la modalité la plus fréquente.",
        "supervision": ("En supervisé, on supprime aussi les lignes sans cible : on ne peut pas "
                        "apprendre d'un exemple dont on ignore la réponse."
                        if ctx.supervised else
                        "En non supervisé, il n'y a pas de cible à protéger : on nettoie l'ensemble "
                        "des variables descriptives."),
    }


def _transform(ctx):
    fe = ("Exemple métier de ce jeu : l'âge d'un bien = année de vente − année de construction, "
          "ou un indicateur binaire de rénovation." if ctx.problem_type == REGRESSION else
          "On crée si possible des variables dérivées plus informatives que les variables brutes.")
    return {
        "why": "Les algorithmes comparent des nombres. Une variable en milliers (le revenu) "
               "écraserait une variable en unités (l'âge) sans remise à l'échelle.",
        "dataset_logic": "On standardise les quantitatives (moyenne 0, écart-type 1), on encode "
                         "les catégorielles en numérique (ordinal ou one-hot), et on redresse les "
                         "distributions très asymétriques. " + fe,
        "supervision": "Cette étape est identique en supervisé et non supervisé : elle prépare la "
                       "représentation numérique des variables, indépendamment d'une cible.",
    }


def _integrate(ctx):
    return {
        "why": "Trop de variables, ou des variables redondantes, ajoutent du bruit et favorisent "
               "le sur-apprentissage. On assemble la matrice finale en retirant la redondance.",
        "dataset_logic": "Deux variables très corrélées portent la même information : on n'en garde "
                         "qu'une. On peut sélectionner les variables les plus informatives ou "
                         "compresser par ACP (composantes principales).",
        "supervision": ("En supervisé, quand deux variables sont redondantes on garde celle la plus "
                        "corrélée à la cible, et la sélection se fait par score univarié vs la cible."
                        if ctx.supervised else
                        "En non supervisé, la redondance se juge sans cible : on garde la diversité "
                        "des variables qui structurent les groupes."),
    }


def _separate(ctx):
    if ctx.supervised:
        return {
            "why": "C'est l'étape qui sépare l'apprentissage de la mesure honnête de la performance.",
            "dataset_logic": "On sépare X (les variables descriptives) de Y (la cible connue), puis "
                             "on découpe en train (pour apprendre) et test (pour mesurer la "
                             "généralisation sur des données jamais vues).",
            "supervision": "APPRENTISSAGE SUPERVISÉ — il existe une cible Y. En classification on "
                           "stratifie pour conserver la proportion des classes dans chaque jeu. On "
                           "contrôle aussi la fuite : une variable quasi identique à la cible "
                           "tricherait.",
        }
    return {
        "why": "En non supervisé, il n'y a rien à prédire : la notion de train/test n'a pas de sens.",
        "dataset_logic": "On conserve la matrice complète des variables standardisées. L'objectif "
                         "est de découvrir une structure cachée (des groupes), pas de prédire un "
                         "label connu.",
        "supervision": "APPRENTISSAGE NON SUPERVISÉ — PAS de cible Y, donc PAS de découpage "
                       "train/test. On ne compare aucune prédiction à une vérité terrain.",
    }


def _model(ctx):
    if ctx.problem_type == REGRESSION:
        body = ("On entraîne un modèle à prédire une valeur continue (ex. un prix). Plusieurs "
                "algorithmes sont comparés : régression linéaire, forêt aléatoire, gradient boosting.")
        sup = "Supervisé — régression : la cible est numérique."
    elif ctx.problem_type == CLASSIFICATION:
        body = ("On entraîne un modèle à prédire une classe (ex. malin / bénin). Plusieurs "
                "algorithmes sont comparés : régression logistique, forêt aléatoire, gradient boosting.")
        sup = "Supervisé — classification : la cible est une catégorie."
    else:
        body = ("KMeans regroupe les observations en K groupes selon leur proximité dans l'espace "
                "des variables. K est choisi (ici par la méthode du coude). Aucun label n'est utilisé.")
        sup = "Non supervisé : aucun label n'entre dans l'entraînement."
    return {"why": "On ajuste l'algorithme aux données préparées.", "dataset_logic": body,
            "supervision": sup}


def _evaluate(ctx):
    if ctx.problem_type == REGRESSION:
        return {
            "why": "On mesure la performance sur le jeu de TEST, jamais vu pendant l'entraînement.",
            "dataset_logic": "R² (part de variance expliquée) et RMSE (erreur moyenne). Le nuage "
                             "réel vs prédit et les résidus révèlent les biais du modèle.",
            "supervision": "Supervisé : la mesure compare la prédiction à la vérité terrain du test.",
        }
    if ctx.problem_type == CLASSIFICATION:
        return {
            "why": "On mesure la performance sur le jeu de TEST, jamais vu pendant l'entraînement.",
            "dataset_logic": "Accuracy et F1, et surtout la matrice de confusion : qui se trompe sur "
                             "quoi (faux positifs / faux négatifs).",
            "supervision": "Supervisé : la mesure compare la prédiction à la vérité terrain du test.",
        }
    return {
        "why": "Sans vérité terrain, on évalue autrement et on donne du SENS aux groupes trouvés.",
        "dataset_logic": "Score de silhouette (cohésion/séparation interne), projection ACP des "
                         "clusters, puis — étape clé — INTERPRÉTATION MÉTIER à partir des profils "
                         "moyens : ex. « Premium fidèle », « Digital promo », « Famille pragmatique ». "
                         "C'est l'interprétation qui crée la valeur.",
        "supervision": "Non supervisé : pas de score contre une vérité, mais une lecture métier des "
                       "clusters.",
    }


def _tune(ctx):
    return {
        "why": "Les hyperparamètres par défaut sont rarement optimaux ; on les cherche méthodiquement.",
        "dataset_logic": "GridSearchCV essaie chaque combinaison d'une grille (ex. learning_rate × n_estimators) "
                         "et mesure la performance par validation croisée (cv plis) sur le train — le test reste intact.",
        "supervision": "Supervisé uniquement : la validation croisée s'appuie sur la cible connue. Le meilleur "
                       "modèle remplace la baseline pour l'Évaluation et l'Explicabilité.",
    }


def _explain(ctx):
    return {
        "why": "Un bon score ne suffit pas : il faut comprendre POURQUOI le modèle prédit ce qu'il prédit.",
        "dataset_logic": "SHAP attribue à chaque variable sa contribution. L'importance globale (barre) classe les "
                         "variables ; le waterfall décompose une prédiction individuelle.",
        "supervision": "Supervisé, modèles à base d'arbres (TreeExplainer). Aide aussi à repérer une variable "
                       "suspecte (fuite) qui dominerait les prédictions.",
    }


_MAP = {
    "clean": _clean,
    "transform": _transform,
    "integrate": _integrate,
    "separate": _separate,
    "model": _model,
    "tune": _tune,
    "evaluate": _evaluate,
    "explain": _explain,
}
