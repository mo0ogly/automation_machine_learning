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
| **5. Modélisation** (`stages/model.py`) | Supervisé : `R²/Accuracy (validation croisée, train) par modèle` (leaderboard CV — le test reste vierge). Clustering : `Méthode du coude — choix de K` + `Graphe k-distance — calibrer eps (DBSCAN)` | Supervisé : `Importance des variables (top 12)`. Agglomératif : `Méthode du coude` + `Dendrogramme (Ward) — fusions hiérarchiques` ; messages selon le cas |
| **6. Fine-tuning** (`stages/tune.py`) | — | `Score CV par combinaison d'hyperparamètres (top 10)` |
| **7. Évaluation** (`stages/evaluate.py`) | — | Régression : `Réel vs Prédit` + `Résidus` + `Courbe d'apprentissage`. Classification : `Matrice de confusion` + `Courbe ROC (jeu de test)` + `Courbe précision-rappel (jeu de test)` (binaire) + `Contrôle du surapprentissage (train / test / CV)` + `Courbe d'apprentissage` + **vue opérationnelle** (`Précision / rappel / F2 selon le seuil`, `Coût opérationnel attendu selon le seuil`, `Diagramme de fiabilité`, `Budget d'alertes`). Clustering : `Clusters (projection PCA)` + `Profil moyen des clusters (écarts standardisés)`. Anomalies : `Distribution des scores d'anomalie` + `Anomalies (projection PCA)` + `Volume d'alertes selon le seuil d'anomalie` |
| **8. Explicabilité** (`stages/explain.py`) | — | SHAP : summary + waterfall (TreeExplainer pour les arbres, LinearExplainer pour Linear/Ridge/Lasso/Logistic ; message sinon) + **dépendance partielle (PDP)** : `Dépendance partielle — <var>` (1D, top variables SHAP) + `Dépendance partielle 2D — <a> × <b>` (surface, interactions) + `Courbes individuelles (ICE) — <var>` (optionnel) + `Interactions entre variables` (valeurs d'interaction SHAP, arbres uniquement, optionnel) via `explain_plots.py` |

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
- **R²/Accuracy (validation croisée, train) par modèle** — leaderboard : chaque candidat
  est classé par validation croisée k-fold SUR LE TRAIN uniquement (moyenne ± écart-type) ;
  le jeu de test n'est jamais consulté avant l'Évaluation.
- **Importance des variables (top 12)** — poids de chaque variable dans le modèle.
- **Méthode du coude — choix de K** — inertie vs K ; le « coude » suggère le bon K.
- **Graphe k-distance — calibrer eps (DBSCAN)** — distance au k-ᵉ voisin triée ; le
  coude donne `eps`.
- **Dendrogramme (Ward) — fusions hiérarchiques** (agglomératif, résultat) — chaque fusion
  de clusters et sa distance ; couper là où les branches verticales sont les plus longues
  valide le K choisi (échantillonné à 300 lignes au-delà).

### Fine-tuning
- **Score CV par combinaison d'hyperparamètres (top 10)** — performance en validation
  croisée par configuration ; la meilleure combinaison ressort.

### Évaluation
- **Réel vs Prédit** (régression) — nuage ; idéal = sur la diagonale ; l'écart = erreur.
- **Résidus** — erreurs vs prédictions ; doivent être centrées sur 0, sans structure.
- **Matrice de confusion** (classification) — vrais/faux positifs et négatifs par classe.
- **Contrôle du surapprentissage (train / test / CV)** — écart train vs test ; grand
  écart = surapprentissage.
- **Courbe ROC (jeu de test)** (classification binaire) — taux de vrais positifs vs faux
  positifs ; AUC proche de 1 = bon classifieur, 0.5 = hasard.
- **Courbe précision-rappel (jeu de test)** (classification binaire) — la lecture honnête
  quand les classes sont déséquilibrées ; la ligne « hasard » vaut la prévalence.
- **Courbe d'apprentissage — plus de données aiderait-il ?** — scores train/CV vs taille
  d'entraînement ; courbes qui convergent encore = plus de données aiderait ; plateau =
  changer de famille de modèle ou de variables.
- **Clusters (projection PCA)** — clusters projetés en 2D (séparation visuelle).
- **Profil moyen des clusters (écarts standardisés)** — ce qui caractérise chaque cluster.
- **Distribution des scores d'anomalie** / **Anomalies (projection PCA)** — scores et
  points jugés anormaux.

### Évaluation opérationnelle (SOC / threat intel — `operational_plots.py`)
- **Précision / rappel / F2 selon le seuil** — arbitrage détection vs fausses alertes ; les
  points recommandés (coût min, FPR 1%) sont marqués. Baisser le seuil = plus de détection,
  plus de fausses alertes.
- **Coût opérationnel attendu selon le seuil** — coût = FN×coût(FN) + FP×coût(FP) ; le minimum
  donne le seuil coût-optimal (en cyber, un raté coûte plus qu'une fausse alerte).
- **Diagramme de fiabilité** — probabilité prédite vs fréquence observée ; sur la diagonale =
  calibré (un score de 0.8 = ~80% de vrais positifs). Brier / ECE en sous-titre.
- **Budget d'alertes** — précision@k (pureté de la file) et détection@k (couverture) selon le
  nombre d'alertes revues, triées par score.
- **Volume d'alertes selon le seuil d'anomalie** (non supervisé) — alertes pour 1000 événements
  par quantile de score, faute de vérité terrain.

### Surveillance post-déploiement (`monitoring_plots.py` — panneau Surveillance, hors badge d'étape)
- **Dérive des données par variable (top)** — PSI par variable (barres, colorées par
  niveau), seuils 0.1 (modérée) et 0.25 (majeure) en pointillés. *Lecture :* les variables
  au-delà de 0.25 ont changé de distribution → le modèle voit des données qu'il ne connaît pas.
- **Dérive de concept : distribution des prédictions** — proportions de chaque classe prédite,
  référence vs lot courant (TVD en titre). *Lecture :* un saut du taux d'alertes = le « normal »
  du détecteur a bougé.
- **Stabilité sous perturbation (protocole jitter)** — taux de bascule des verdicts vs amplitude
  du bruit (log, fractions de l'écart-type par variable), bande min-max sur les répétitions,
  tolérance 5 % et point de rupture marqués. *Lecture :* une courbe qui franchit la tolérance à
  gauche (petites amplitudes) = détecteur instable en environnement critique. Propriétaire :
  `monitoring_plots.jitter_plot` — ne pas dupliquer dans l'Évaluation.

### Analyses de stabilité avancées (`stability_plots.py` — cartes du panneau Surveillance)
- **Jitter numérique : écarts de score float32 vs float64** — histogramme des |Δscore|.
  *Lecture :* des écarts non négligeables + des points près du seuil = verdicts dépendants de
  l'environnement arithmétique.
- **Marges au seuil de décision** — histogramme des distances normalisées au seuil, bande 5 %
  marquée. *Lecture :* la masse à gauche = la population qu'une perturbation quelconque ferait
  basculer en premier.
- **Churn de ré-entraînement** — barres de désaccord vs modèle déployé, une par seed, repère 5 %.
  *Lecture :* churn élevé = famille de modèle structurellement instable sur ces données.
- **Prédiction conforme** — classification : proportions par taille d'ensemble (1 = net,
  ≥ 2 = ambigu, 0 = hors distribution) ; anomalie : histogramme des p-values conformes ;
  régression : résidus de calibration + demi-largeur garantie. *Lecture :* la part ambiguë =
  les verdicts à router vers un analyste.
- **Robustesse certifiée (randomized smoothing)** — fraction certifiée vs rayon (unités :
  écart-type par variable). *Lecture :* la courbe donne, pour chaque rayon de perturbation, la
  part des verdicts garantis inchangés (classifieur lissé, Cohen 2019).

### Explicabilité
- **SHAP summary** — contribution (et direction) de chaque variable aux prédictions, globalement.
- **Dépendance partielle — <var>** (1D) — forme de l'effet MOYEN d'une variable sur la
  prédiction quand elle varie (monotone ? seuil ? non linéaire ?). Complète SHAP (qui donne
  l'importance, pas la forme).
- **Dépendance partielle 2D — <a> × <b>** — surface pour une PAIRE de variables ; met en
  évidence les interactions qu'une vue additive manquerait.
- **Courbes individuelles (ICE) — <var>** (optionnel) — une courbe par observation + la
  moyenne PDP ; révèle des sous-groupes qui réagissent différemment (hétérogénéité).
- **Interactions entre variables** (optionnel, arbres) — force d'interaction SHAP des paires
  de variables les plus liées ; pendant global de la dépendance partielle 2D.
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
