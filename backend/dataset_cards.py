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

    # ── New: prompt-injection detection (text -> tabular features) ───────
    "prompt_injection.csv": {
        "title": "Détection d'injection de prompt — prévoir les attaques",
        "type": "Classification binaire (injection / benign)",
        "synthetic": True,
        "rows": 1000, "cols": 18,
        "target": "label — injection / benign",
        "source": (
            "Corpus synthétique d'injection indirecte (1000 segments), aligné OWASP LLM 2025 "
            "(LLM01:2025) et Greshake et al. (2023). Brut : data/sources/prompt-injection-corpus.jsonl."
        ),
        "summary": (
            "Détecter les instructions malveillantes dissimulées dans de la donnée qu'un agent LLM "
            "ingère (e-mails, pages web, passages RAG, sorties d'outils). Le corpus brut est du texte ; "
            "comme la plateforme est tabulaire, chaque texte est converti en variables de surface "
            "interprétables et SANS fuite (longueur, mots-déclencheurs, marqueurs de délimiteurs, "
            "caractères de largeur nulle, blobs base64, URLs…), plus le canal et la langue. Objectif : "
            "apprendre la frontière entre instruction de confiance et donnée non fiable."
        ),
        "sections": [
            {"heading": "Schéma — variables (features de surface)", "table": [
                ["text_length / word_count / line_count", "Taille du segment (caractères, mots, lignes)"],
                ["avg_word_length / max_token_length", "Longueur moyenne / max d'un token (tokens longs = base64/URL)"],
                ["uppercase_ratio / digit_ratio / punct_ratio", "Densité de majuscules, chiffres, ponctuation"],
                ["trigger_keyword_count", "Mots d'annulation/d'ordre (ignore, disregard, instructions…), multilingue"],
                ["role_keyword_count", "Réassignation de rôle (system, admin, developer mode, root…)"],
                ["delimiter_marker_count", "Faux délimiteurs / barrières de prompt (```, <|, [INST], END OF…)"],
                ["zero_width_count / non_ascii_ratio", "Signaux d'obfuscation (espaces de largeur nulle, homoglyphes)"],
                ["url_count / has_base64_blob", "Présence d'URL / de charge encodée en base64"],
                ["carrier", "Canal porteur (email, web_page, rag_chunk, tool_output…) — observable"],
                ["language", "Langue du document hôte : en / fr / pt — observable"],
                ["label", "Cible : injection / benign (550 / 450)"],
            ]},
            {"heading": "Cible & absence de fuite", "text": (
                "Cible binaire label (injection 55% / benign 45%). Les métadonnées du corpus brut qui "
                "décrivent la charge (technique, owasp_llm, obfuscation, severity, boundary, "
                "payload_span, cross_lingual, code_switched, benign_subtype) sont nulles ssi le texte "
                "est bénin : les utiliser pour prédire label = fuite de cible. Elles sont donc retirées. "
                "Seules les variables calculées depuis le texte (observables à l'inférence) et le canal / "
                "la langue (présents pour les deux classes) sont conservés."
            )},
            {"heading": "Pourquoi un modèle bat les mots-clés", "text": (
                "Le corpus inclut des hard negatives (texte bénin contenant des mots déclencheurs) et un "
                "sous-type injection_discussion (texte qui parle d'injection sans la perpétrer). Une "
                "règle mono-mot s'effondre dessus : ici trigger_keyword_count > 0 seul donne ~0.50 "
                "d'accuracy. Un modèle qui combine les variables sépare correctement attaque et donnée "
                "bénigne, y compris sur ces confuseurs."
            )},
            {"heading": "Recommandations ML", "text": (
                "One-hot pour carrier / language, le reste est numérique. Découpage stratifié sur label. "
                "Repère sans fuite (RandomForest, CV 5 plis) : accuracy ≈ 0.98, F1 macro ≈ 0.98 — plafond "
                "élevé sur découpage aléatoire car les charges synthétiques sont régulières. Pour un test "
                "exigeant, évaluer la généralisation inter-langue (entraîner en, tester fr/pt) ou "
                "régénérer le CSV via data/generators/prompt_injection.py."
            )},
        ],
    },

    # ── New: prompt-injection attack-type classification ────────────────
    "prompt_injection_technique.csv": {
        "title": "Type d'injection de prompt — quelle technique d'attaque",
        "type": "Classification multiclasse (12 techniques)",
        "synthetic": True,
        "rows": 550, "cols": 18,
        "target": "technique — 12 mécanismes d'injection",
        "source": (
            "Mêmes 550 injections que prompt_injection.csv (corpus synthétique aligné OWASP LLM 2025). "
            "Brut : data/sources/prompt-injection-corpus.jsonl ; généré par data/generators/prompt_injection.py."
        ),
        "summary": (
            "Second modèle, complémentaire de la détection binaire : une fois qu'on sait qu'un texte "
            "est une attaque, de quel TYPE s'agit-il ? Restreint aux 550 injections, avec les mêmes "
            "variables de surface sans fuite, et pour cible le mécanisme (instruction_override, "
            "data_exfiltration, role_hijack, tool_abuse…). Tâche volontairement plus difficile que la "
            "détection : illustre la montée en difficulté quand le nombre de classes augmente."
        ),
        "sections": [
            {"heading": "Schéma — variables", "table": [
                ["text_length / word_count / line_count", "Taille du segment"],
                ["trigger_keyword_count / role_keyword_count", "Mots d'ordre / de réassignation de rôle"],
                ["delimiter_marker_count", "Faux délimiteurs / barrières de prompt"],
                ["url_count / has_base64_blob", "URL (indice d'exfiltration) / charge encodée"],
                ["zero_width_count / non_ascii_ratio", "Signaux d'obfuscation"],
                ["uppercase_ratio / digit_ratio / punct_ratio", "Densités typographiques"],
                ["carrier / language", "Canal porteur et langue (observables)"],
                ["technique", "Cible : 12 techniques équilibrées (~42–49 exemples chacune)"],
            ]},
            {"heading": "Les 12 classes", "text": (
                "instruction_override, delimiter_injection, role_hijack, system_prompt_leak, "
                "data_exfiltration, tool_abuse, conditional_trigger, refusal_suppression, fake_authority, "
                "output_manipulation, misinformation_seed, staged_multistep. Réparties équitablement "
                "(45 ± 3 par classe), pas de classe minoritaire écrasante."
            )},
            {"heading": "Absence de fuite", "text": (
                "Les colonnes owasp_llm, severity, boundary, payload_span du corpus brut sont des "
                "corollaires directs de technique — elles sont retirées. Seules les variables calculées "
                "depuis le texte et le canal / la langue sont conservées : aucune ne désigne la technique, "
                "qui dépend de l'intention de la charge, pas d'une étiquette annexe."
            )},
            {"heading": "Recommandations ML", "text": (
                "One-hot pour carrier / language. Découpage stratifié sur technique (12 classes). Repère "
                "sans fuite (RandomForest, CV 5 plis) : accuracy ≈ 0.46, F1 macro ≈ 0.46 — soit ~5,5× le "
                "hasard (1/12 ≈ 0.083). Suivre la matrice de confusion : les techniques au signal de "
                "surface marqué (data_exfiltration via URL, delimiter_injection via délimiteurs) se "
                "séparent mieux que celles définies surtout par la sémantique."
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
