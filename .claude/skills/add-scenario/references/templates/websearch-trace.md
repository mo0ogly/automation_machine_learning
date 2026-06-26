# Template : Web Search Trace
# Utilisé par : Scientist sub (Phase 3) + Phase 1a
# Règle : OBLIGATOIRE — chaque recherche produit une trace, même résultat nul
# Fichier cible : research_archive/data/references/scenario_{scenario_id}_refs.md

## WebSearch Trace — {query_string} — {YYYY-MM-DD HH:MM}

- Source : {url ou "no relevant result found"}
- Extrait : {passage pertinent en 1-3 phrases, ou "N/A — query returned no useful results"}
- Clé BibTeX : {clé ou "none"}
- Gap comblé : {yes — absent de ChromaDB | no — déjà couvert | N/A}
- Utilisé dans : {quelle section du doc cette référence supporte, ex: "formal_framework §6.bis" | "RETEX open questions" | "none"}

---

# NOTES D'USAGE

## Quand créer une trace

Toujours — la trace fait partie de la méthodologie, pas du résultat.

| Situation | Trace requise ? |
|-----------|----------------|
| Bon résultat trouvé | OUI — trace complète |
| Résultat partiel / tangentiel | OUI — noter "tangential, not cited" |
| Aucun résultat pertinent | OUI — écrire "no relevant result found" |
| Recherche sautée (gap_detected=false) | OUI — écrire "skipped: ChromaDB coverage sufficient" |

## Tags d'anomalie (ajouter si détecté)

Ajouter un de ces tags sur la ligne de trace si applicable :

| Tag | Signification |
|-----|--------------|
| `[ANOMALY:BROKEN_URL]` | URL retourne 404 ou timeout |
| `[ANOMALY:DUPLICATE_REF]` | Même URL déjà citée sous une clé différente |
| `[ANOMALY:MISSING_BIBTEX]` | Source sans BibTeX citable (blog, forum, etc.) |
| `[ANOMALY:PREPRINT]` | Source est un preprint — noter version/DOI |

Ces tags sont consommés par le RETEX Synthesis pour générer les counts d'anomalies.

## Template BibTeX (ajouter quand source citable trouvée)

```bibtex
@{article|misc|inproceedings}{key,
  author  = {},
  title   = {},
  year    = {},
  doi     = {},
  url     = {},
  note    = {Accessed {YYYY-MM-DD}. Context: {scenario_id}}
}
```

## Notation

Utiliser δ⁰ δ¹ δ² δ³ dans les extraits et analyses. Jamais δ⁰/1/2/3 ASCII.
