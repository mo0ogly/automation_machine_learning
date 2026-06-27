# Catalogue des graphes du pipeline — source de vérité

But de ce document : recenser **quels graphes chaque étape produit**, pour
(1) éviter de recréer un graphe qui existe déjà à une autre étape, et
(2) savoir d'où vient chaque chiffre du badge « Graphiques **N** ».

> À relire **avant** d'ajouter un graphe à une étape : vérifier ici qu'il
> n'existe pas déjà ailleurs (ex. les distributions par variable sont à la
> **Transformation** — ne pas les dupliquer au Nettoyage).

## Comment compter (badge « Graphiques N »)

Le badge de l'onglet **Graphiques** d'une étape = **graphes de diagnostic**
(`diagnose_plots`, visibles sans exécuter) **+ graphes de résultat**
(`result.plots`, ajoutés après avoir exécuté l'étape).

- Avant exécution : badge = nombre de graphes de diagnostic.
- Après exécution : badge = diagnostic + résultat.

C'est pourquoi le nombre « monte » quand on exécute une étape (ex. Nettoyage
31 → 32). Ce n'est pas un bug.

## Répartition par étape (ne pas dupliquer entre étapes)

| Étape | Diagnostic (sans exécuter) | Résultat (après exécution) |
|-------|----------------------------|----------------------------|
| **1. Nettoyage** (`stages/clean.py`) | `Valeurs manquantes par colonne (%)` (1 barre) + `Aberrants — <var> (N hors IQR)` : **une boîte à moustaches par variable numérique** (≤ 30, triées par variance) | `Nettoyage : manquant global` (avant/après, 1) |
| **2. Transformation** (`stages/transform.py`) | `Distribution : <col>` (asymétrie, 1) + **univarié par variable** (`Distribution — <var>` continues, `Effectifs — <var>` discrètes/nominales) + **bivarié par variable** (`<cible> selon <var>`) | `<col> — avant` / `<col> — après` (1 figure) |
| **3. Intégration** (`stages/integrate.py`) | `Corrélations entre variables` (heatmap) + `\|Corrélation\| avec la cible` (barres) + `Analyse bivariée : <feature> vs <cible>` (nuage) | `Corrélations entre variables` (heatmap) |
| **4. Séparation** (`stages/separate.py`) | `Classes de <cible>` ou `Distribution de <cible>` (1) | `Équilibre des classes par jeu` ou `Distribution de la cible par jeu` (1) |
| **5. Modélisation** (`stages/model.py`) | Supervisé : `Importance des variables (top 12)` / classement. Clustering : `Méthode du coude — choix de K` + `Graphe k-distance — calibrer eps (DBSCAN)` | messages selon le cas |
| **6. Fine-tuning** (`stages/tune.py`) | — | `Score CV par combinaison d'hyperparamètres (top 10)` |
| **7. Évaluation** (`stages/evaluate.py`) | — | Régression : `Réel vs Prédit` + `Résidus`. Classification : `Matrice de confusion` + `Contrôle du surapprentissage (train / test / CV)`. Clustering : `Clusters (projection PCA)` + `Profil moyen des clusters (écarts standardisés)`. Anomalies : `Distribution des scores d'anomalie` + `Anomalies (projection PCA)` |
| **8. Explicabilité** (`stages/explain.py`) | — | SHAP : summary + waterfall (ou message si modèle non arborescent) |

## Règles anti-doublon (qui fait quoi)

Chaque type de graphe a **une seule étape propriétaire** :

- **Distributions par variable** (histogrammes / effectifs) → **Transformation**
  (`eda_plots.univariate_plots`). NE PAS les remettre au Nettoyage.
- **Relations variable ↔ cible** (bivarié) → **Transformation**
  (`eda_plots.bivariate_plots`).
- **Aberrants / bornes IQR** (boîtes à moustaches par variable) → **Nettoyage**
  (`clean._boxplot_per_variable`). Spécifique qualité des données.
- **Valeurs manquantes** → **Nettoyage**.
- **Corrélations entre variables / avec la cible** → **Intégration**.
- **Équilibre / split train-test** → **Séparation**.
- **Performance du modèle** (confusion, résidus, PCA, surapprentissage) → **Évaluation**.
- **Importance des variables** → **Modélisation** (globale) et **Explicabilité** (SHAP).

## Comment lire chaque graphe

### Nettoyage
- **Valeurs manquantes par colonne (%)** — barres horizontales, une par colonne,
  triées par taux de manquant. *Lecture :* en haut = les plus incomplètes.
  *Décision :* > 50 % manquant → retirer la colonne ; sinon → imputer.
- **Aberrants — <var> (N hors IQR)** — boîte à moustaches. La boîte couvre Q1→Q3
  (50 % central), le trait est la médiane, les moustaches vont à 1,5×IQR, les
  points au-delà sont les aberrants ; *N hors IQR* est leur nombre. *Décision :*
  beaucoup de points / longues moustaches → borner (IQR) ou supprimer les aberrants.
- **Nettoyage : manquant global** (résultat) — % de cellules manquantes avant vs
  après. *Lecture :* « après » doit être ~0 si l'imputation a fonctionné.

### Transformation
- **Distribution : <col>** — histogramme de la variable la plus asymétrique.
  *Décision :* queue longue (skew) → normaliser (log / Box-Cox / Yeo-Johnson).
- **Distribution — <var>** — histogramme par variable continue : forme, étalement, pics.
- **Effectifs — <var>** — nombre d'observations par modalité (discret/nominal).
  *Lecture :* modalités rares ou déséquilibre.
- **<cible> selon <var>** (bivarié) — la cible en fonction de chaque variable.
  *Lecture :* plus la cible varie selon la variable, plus celle-ci est prédictive.
- **<col> — avant / après** (résultat) — effet de la transformation sur la distribution.

### Intégration
- **Corrélations entre variables** (heatmap) — corrélation deux à deux. *Lecture :*
  cases vives = variables redondantes (colinéarité). *Décision :* retirer / PCA.
- **|Corrélation| avec la cible** — force du lien de chaque variable avec la cible
  (les plus prédictives en tête).
- **Analyse bivariée : <feature> vs cible** — nuage de la variable la plus corrélée
  avec la cible (forme de la relation : linéaire, non linéaire…).

### Séparation
- **Classes de <cible>** / **Distribution de <cible>** — répartition de la cible
  (équilibre des classes en classification ; forme en régression).
- **Équilibre des classes par jeu** / **Distribution de la cible par jeu** (résultat)
  — compare train et test. *Lecture :* les deux doivent se ressembler (split représentatif).

### Modélisation
- **Importance des variables (top 12)** — poids de chaque variable dans le modèle.
- **Méthode du coude — choix de K** — inertie vs K ; le « coude » suggère le bon K.
- **Graphe k-distance — calibrer eps (DBSCAN)** — distance au k-ᵉ voisin triée ; le
  coude donne `eps`.

### Fine-tuning
- **Score CV par combinaison d'hyperparamètres (top 10)** — performance en validation
  croisée par configuration ; la meilleure combinaison ressort.

### Évaluation
- **Réel vs Prédit** (régression) — nuage ; idéal = sur la diagonale ; l'écart = erreur.
- **Résidus** — erreurs vs prédictions ; doivent être centrées sur 0, sans structure.
- **Matrice de confusion** (classification) — vrais/faux positifs et négatifs par classe.
- **Contrôle du surapprentissage (train / test / CV)** — écart train vs test ; grand
  écart = surapprentissage.
- **Clusters (projection PCA)** — clusters projetés en 2D (séparation visuelle).
- **Profil moyen des clusters (écarts standardisés)** — ce qui caractérise chaque cluster.
- **Distribution des scores d'anomalie** / **Anomalies (projection PCA)** — scores et
  points jugés anormaux.

### Explicabilité
- **SHAP summary** — contribution (et direction) de chaque variable aux prédictions, globalement.
- **Waterfall** — décomposition d'UNE prédiction : ce qui la pousse vers le haut / le bas.

## Générateurs partagés

- `pipeline/eda_plots.py` : `univariate_plots(df, t)` (un graphe par variable :
  histogramme continu, effectifs discret/nominal) et `bivariate_plots(df, target, t)`
  (un graphe par variable vs cible). **Une figure par variable** — d'où la densité
  (≈ 28 à la Transformation selon le jeu).
- `pipeline/plotting.py` : thème commun (`style_plot`), `fig_to_base64` (sérialise
  + ferme la figure), `message_plot` (placeholder texte). Génération sérialisée par
  `PLOT_LOCK` (matplotlib n'est pas thread-safe).

## Rendu côté frontend

- Onglet dédié **Graphiques** (`components/StagePanel.jsx`) : sections
  « Graphiques — diagnostics » et « Graphiques — résultat de l'étape ».
- `.plot-fig` : **pas** de `content-visibility: auto` (le retirer faisait clignoter
  / disparaître les figures au scroll quand il y en a beaucoup). `decoding="async"`
  sur l'`<img>` garde le décodage hors du thread principal. **Pas** de
  `loading="lazy"` (inutile sur un data-URI base64, et cassait l'affichage).
