"""
dataset_cards.py — per-dataset "data cards" surfaced in the UI.

Each demo dataset has a card explaining what it is, its schema highlights, its
target(s), ML guidance and provenance — the same kind of accompaniment as the
cyber-risk data card. Served by ``GET /api/dataset-card/{name}`` and rendered in
a modal from the start screen.

Card shape (generic so the frontend renders any of them):
    {
      name, title, type, synthetic (bool),
      summary (str), rows, cols, target (str), source (str),
      sections: [ {heading, text} | {heading, table: [[col, desc], ...]} ],
    }
"""

CARDS = {
    # ── New: synthetic cyber-risk prioritisation ────────────────────────
    "cyber_risk.csv": {
        "title": "Risque cyber — priorisation des actifs",
        "type": "Classification multiclasse (4 niveaux)",
        "synthetic": True,
        "rows": 5000, "cols": 20,
        "target": "risk_label — low / medium / high / critical",
        "source": "Signaux inspirés de cadres réels (simulés) : CVSS, EPSS, CISA KEV, BOD 22-01.",
        "summary": (
            "Jeu tabulaire entièrement synthétique de 5000 actifs du SI, pour l'apprentissage du "
            "scoring et de la priorisation des risques cyber. Chaque actif est décrit par son "
            "contexte métier, son exposition, sa surface vulnérable (CVSS, EPSS, CISA KEV), des "
            "signaux d'activité et sa couverture EDR. Construit avec un modèle génératif à "
            "dépendances conditionnelles (pas un tirage i.i.d.) pour une structure de corrélation "
            "crédible et une cible non triviale."
        ),
        "sections": [
            {"heading": "Schéma — variables clés", "table": [
                ["asset_type", "Type d'actif : server, workstation, database, web_app, cloud_vm, firewall"],
                ["segment", "Zone réseau : dmz, server_lan, user_lan, cloud, ot"],
                ["business_criticality", "Criticité métier (ordinale) : low < medium < high < critical"],
                ["data_sensitivity", "Sensibilité (ordinale) : public < internal < confidential < restricted"],
                ["internet_exposed", "Exposition directe sur Internet (0/1)"],
                ["cvss_score", "Sévérité CVSS simulée (0–10)"],
                ["epss_score", "Probabilité d'exploitation EPSS simulée (0–1)"],
                ["known_exploited", "Présence au catalogue CISA KEV (0/1)"],
                ["kev_ransomware", "Usage rançongiciel connu (champ CISA KEV)"],
                ["kev_overdue", "Remédiation au-delà du délai BOD 22-01 (0/1)"],
                ["patch_age_days", "Ancienneté du dernier correctif (0–729 j)"],
                ["edr_coverage", "Couverture EDR (ordinale) : none < partial < full"],
            ]},
            {"heading": "Cibles & fuite de cible", "text": (
                "Deux cibles : risk_score (régression, 0–100) et risk_label (classification, 4 classes "
                "issues du découpage de risk_score sur ses quantiles). Comme risk_label dérive de "
                "risk_score, utiliser l'un pour prédire l'autre = fuite de cible. Pour cette démo on "
                "garde la classification sur risk_label et on retire risk_score ainsi que la clé "
                "asset_id. Répartition : low 15% / medium 40% / high 30% / critical 15%."
            )},
            {"heading": "Modèle de risque (génératif)", "text": (
                "Risque latent = somme pondérée de 4 sous-scores normalisés — menace (CVSS/EPSS/KEV), "
                "exposition (Internet/ports/patch/segment), impact (criticité/sensibilité/privilèges), "
                "signaux (alertes externes/échecs d'auth) — atténué par la couverture EDR, plus un "
                "bruit gaussien, puis mis à l'échelle robuste sur 0–100. Cohérences vérifiées : ports "
                "ouverts ↑ si exposé, taux KEV ↑ avec le quartile EPSS, risk_score ↓ avec l'EDR."
            )},
            {"heading": "Recommandations ML", "text": (
                "Encodage ordinal pour business_criticality / data_sensitivity / edr_coverage (ordre "
                "naturel), one-hot pour les nominales. Découpage stratifié sur risk_label (classe "
                "critical minoritaire). Repère sans fuite (RandomForest, CV 5 plis) : accuracy ≈ 0.67, "
                "F1 macro ≈ 0.66. Une accuracy proche de 1 signalerait une fuite à investiguer."
            )},
        ],
    },

    # ── Existing demos ──────────────────────────────────────────────────
    "house_price_data.csv": {
        "title": "Prix immobiliers — Ames Housing",
        "type": "Régression",
        "synthetic": False,
        "rows": 1460, "cols": 81,
        "target": "SalePrice — prix de vente (continu, USD)",
        "source": "Ames Housing (De Cock, 2011) — biens résidentiels d'Ames, Iowa.",
        "summary": (
            "Jeu de référence pour la régression : 1460 ventes décrites par ~80 variables de surface, "
            "qualité, équipements, année et quartier. Idéal pour l'ingénierie de variables et "
            "l'encodage de notes de qualité ordinales."
        ),
        "sections": [
            {"heading": "Schéma — variables clés", "table": [
                ["OverallQual", "Qualité générale (note ordinale 1–10)"],
                ["GrLivArea", "Surface habitable hors sous-sol (pieds²)"],
                ["Neighborhood", "Quartier (nominale, ~25 modalités)"],
                ["YearBuilt", "Année de construction"],
                ["ExterQual / BsmtQual / KitchenQual", "Notes de qualité ordinales : Po < Fa < TA < Gd < Ex"],
                ["TotalBsmtSF / GarageArea", "Surfaces sous-sol / garage"],
                ["SalePrice", "Cible : prix de vente (continu)"],
            ]},
            {"heading": "Recommandations ML", "text": (
                "Encodage ordinal des notes de qualité (respecter Po<Fa<TA<Gd<Ex), one-hot des "
                "nominales (Neighborhood…). Surveiller les valeurs aberrantes de surface (ex. GrLivArea "
                "> 4000). Métriques typiques : R² ≈ 0.85–0.9 avec un Gradient Boosting / XGBoost."
            )},
        ],
    },

    "breastcancer.csv": {
        "title": "Diagnostic du cancer du sein — Wisconsin (WDBC)",
        "type": "Classification binaire",
        "synthetic": False,
        "rows": 569, "cols": 32,
        "target": "diagnosis — B (bénin) / M (malin)",
        "source": "Wisconsin Diagnostic Breast Cancer (Wolberg et al.) — mesures de noyaux cellulaires.",
        "summary": (
            "Classification binaire de référence : 569 tumeurs décrites par 30 variables numériques "
            "(moyenne, erreur-type et pire valeur de 10 mesures morphologiques de noyaux). Cible "
            "équilibrée ~63% bénin / 37% malin."
        ),
        "sections": [
            {"heading": "Schéma — variables clés", "table": [
                ["radius_mean / perimeter_mean / area_mean", "Taille moyenne des noyaux"],
                ["texture_mean / smoothness_mean", "Texture et régularité"],
                ["concavity_mean / concave points_mean", "Concavités du contour"],
                ["*_se", "Erreur-type de chaque mesure"],
                ["*_worst", "Pire (plus grande) valeur de chaque mesure"],
                ["diagnosis", "Cible : B (bénin) / M (malin)"],
            ]},
            {"heading": "Recommandations ML", "text": (
                "Toutes les variables sont numériques (mise à l'échelle utile pour les modèles "
                "linéaires). Cible légèrement déséquilibrée : suivre précision/rappel et la matrice de "
                "confusion, pas seulement l'accuracy. Repère : accuracy ≈ 0.95+ atteignable."
            )},
        ],
    },

    "Stars.csv": {
        "title": "Types d'étoiles",
        "type": "Classification multiclasse (6 classes)",
        "synthetic": False,
        "rows": 240, "cols": 7,
        "target": "Type — 6 types stellaires (naine brune → hypergéante)",
        "source": "Caractéristiques stellaires (température, luminosité, rayon, magnitude).",
        "summary": (
            "Petit jeu de classification multiclasse : 240 étoiles réparties en 6 types, décrites par "
            "leurs grandeurs physiques. Bon support pour comparer régression logistique, arbres et "
            "forêts sur un problème multiclasse compact."
        ),
        "sections": [
            {"heading": "Schéma", "table": [
                ["Temperature", "Température de surface (K)"],
                ["L", "Luminosité relative au Soleil"],
                ["R", "Rayon relatif au Soleil"],
                ["A_M", "Magnitude absolue"],
                ["Color / Spectral_Class", "Couleur et classe spectrale (catégorielles)"],
                ["Type", "Cible : type stellaire (0–5)"],
            ]},
            {"heading": "Recommandations ML", "text": (
                "Échelles très variables (luminosité, rayon couvrent plusieurs ordres de grandeur) : "
                "une transformation log aide les modèles linéaires. Jeu petit : privilégier la "
                "validation croisée stratifiée."
            )},
        ],
    },

    "client_data.csv": {
        "title": "Segmentation clients",
        "type": "Clustering (non supervisé)",
        "synthetic": True,
        "rows": 600, "cols": 9,
        "target": "Aucune — apprentissage non supervisé (découverte de segments)",
        "source": "Jeu synthétique de démonstration (segmentation comportementale).",
        "summary": (
            "Jeu sans cible pour le clustering : 600 clients décrits par leur comportement d'achat et "
            "leur engagement. Objectif : découvrir des segments (KMeans / DBSCAN / agglomératif) et "
            "les lire en valeurs métier (table de décision pour les nommer)."
        ),
        "sections": [
            {"heading": "Schéma", "table": [
                ["client_id", "Identifiant (clé, à retirer)"],
                ["age / revenu_annuel_k", "Âge et revenu annuel (k€)"],
                ["frequence_achat_mois / panier_moyen", "Fréquence d'achat et panier moyen"],
                ["score_engagement / sensibilite_promo", "Engagement et sensibilité aux promotions"],
                ["canal_prefere / region", "Canal préféré et région (catégorielles)"],
            ]},
            {"heading": "Recommandations ML", "text": (
                "Retirer client_id, mettre à l'échelle les variables numériques (sinon le revenu "
                "domine la distance). Choisir K par la méthode du coude + silhouette. Lire les centres "
                "en valeurs brutes pour donner un nom métier à chaque segment."
            )},
        ],
    },

    "transactions.csv": {
        "title": "Transactions — détection d'anomalies",
        "type": "Détection d'anomalies (non supervisé)",
        "synthetic": True,
        "rows": 300, "cols": 5,
        "target": "Aucune — détection non supervisée d'observations atypiques",
        "source": "Jeu synthétique reproductible (data/generators/transactions.py, graines 42/7).",
        "summary": (
            "Jeu sans cible pour la détection d'anomalies : 300 transactions dont ~5% atypiques "
            "(montants, fréquence et géographie inhabituels). Objectif : isoler les anomalies "
            "(Isolation Forest / LOF) sans étiquettes."
        ),
        "sections": [
            {"heading": "Schéma", "table": [
                ["montant_eur", "Montant de la transaction (€)"],
                ["frequence_mensuelle", "Nombre de transactions par mois"],
                ["anciennete_mois", "Ancienneté du compte (mois)"],
                ["nb_pays", "Nombre de pays distincts"],
                ["ratio_nuit", "Part des transactions de nuit (0–1)"],
            ]},
            {"heading": "Recommandations ML", "text": (
                "Aucune étiquette : on ne mesure pas une accuracy mais un taux d'anomalies plausible "
                "(~5%). Isolation Forest / LOF donnent un score d'anomalie ; inspecter le top des "
                "scores. Régénérable à l'identique via data/generators/transactions.py."
            )},
        ],
    },
}


def get(name: str):
    """Return the card for a dataset (with its ``name`` field set), or ``None``."""
    card = CARDS.get(name)
    if card is None:
        return None
    return {"name": name, **card}


def summary_for(name: str):
    """One-line summary used in the demo list (or empty)."""
    card = CARDS.get(name)
    return card["summary"] if card else ""
