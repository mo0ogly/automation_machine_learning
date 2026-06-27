# Modèle exporté — AEGIS / automation_machine_learning

Bundle Python autonome d'un modèle entraîné. Les prédictions sont **identiques**
à celles de l'application : le bundle embarque le code de transformation du projet
(`aegis_pipeline/`) et re-dérive le preprocessing exact à partir des données
d'entraînement (`training_data.csv`), comme le fait le serveur.

## Contenu

| Fichier | Rôle |
|---------|------|
| `model.joblib` | Modèle entraîné (+ encodeur de labels, artefacts de clustering) |
| `training_data.csv` | Données d'origine sur lesquelles le preprocessing se re-calibre |
| `config.json` | Type de problème, cible, configs des étapes, noms de features, classes |
| `aegis_pipeline/` | Code de serving authentique (clean / transform / integrate / scoring) |
| `predict.py` | Scoreur turnkey (CSV brut -> CSV enrichi) |
| `requirements.txt` | Versions épinglées de cet environnement (reproduction fidèle) |

## Utilisation

```bash
pip install -r requirements.txt
python predict.py mes_lignes.csv
# -> mes_lignes_scored.csv  (+ résumé de distribution affiché)
```

`mes_lignes.csv` contient des lignes **brutes** : les colonnes d'origine (les mêmes
que les données d'entraînement). Les colonnes manquantes sont complétées par des
valeurs par défaut raisonnables (médiane / modalité majoritaire).

La sortie ajoute une colonne `prediction` (+ `confidence` en classification,
`anomaly_score` en détection d'anomalies).

## Usage programmatique

```python
import pandas as pd
from predict import load_session
from aegis_pipeline import scoring

df = pd.DataFrame([{ "colonne_a": 12.3, "colonne_b": "X" }])
enriched, summary = scoring.score_dataframe(load_session(), df)
print(enriched[["prediction"]])
```

## Notes

- Pour une reproduction au bit près, utilisez exactement les versions de
  `requirements.txt` (un changement de version de scikit-learn peut décaler les
  valeurs à la marge).
- Le bundle ne dépend ni d'un réseau ni du serveur AEGIS : il est autonome.
