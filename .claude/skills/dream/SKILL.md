---
name: dream
description: >
  Memory consolidation skill inspired by Anthropic's autoDream. Audits and consolidates
  Claude Code memory files — detects orphans, stale entries, credentials, duplicates,
  and performs semantic merging. Use when: "dream", "consolidate memory", "clean memory",
  "memory audit", "nettoyer la memoire", end-of-session cleanup.
metadata:
  user_invocable: "true"
  argument_hint: "[audit|consolidate|full]"
---

# /dream — Memory Consolidation

Phase "dream" inspiree d'autoDream : nettoyage et consolidation de la memoire Claude Code.

## Modes

| Mode | Commande | Action |
|------|----------|--------|
| audit | `/dream audit` | Lance le script d'audit mecanique, affiche le rapport |
| consolidate | `/dream consolidate` | Audit + consolidation semantique automatique |
| full | `/dream full` ou `/dream` | Audit + consolidate + verification post-consolidation |

## Etape 1 : Audit mecanique

Lancer le script d'audit adapte a la plateforme :
- **Windows** : `powershell.exe -ExecutionPolicy Bypass -File .claude/scripts/dream-audit.ps1`
- **Linux/macOS** : `bash .claude/scripts/dream-audit.sh`

Le script verifie :
1. **Index sync** : fichiers orphelins / references cassees dans MEMORY.md
2. **Taille index** : >150 lignes = warning, >200 = erreur
3. **Staleness** : fichiers >30 jours = stale, >14 jours = aging
4. **Credentials** : patterns password/secret/token/api_key dans les .md
5. **Doublons** : descriptions identiques dans le frontmatter
6. **Compteurs** : nombre de fichiers, lignes totales

Verdict : `CLEAN` (exit 0) / `NEEDS_CONSOLIDATION` (exit 1) / `CRITICAL` (exit 2)

Si le verdict est CLEAN et le mode est `audit` : terminer ici.

## Etape 2 : Consolidation semantique

Si le verdict est NEEDS_CONSOLIDATION ou CRITICAL, ou si le mode est `consolidate` ou `full` :

### 2.1 — Lire tous les fichiers memoire
Lire chaque .md dans le repertoire memoire (sauf MEMORY.md).

### 2.2 — Detecter les doublons semantiques
Comparer les fichiers par sujet. Deux fichiers sont candidats a la fusion si :
- Meme `type:` dans le frontmatter ET sujets proches
- Exemple : `project_x_v1.md` et `project_x_update.md` sur le meme projet

### 2.3 — Fusionner les redondances
Pour chaque paire de doublons :
- Garder le fichier le plus recent comme base
- Integrer les informations uniques de l'ancien
- Supprimer l'ancien fichier
- Mettre a jour MEMORY.md

### 2.4 — Convertir les dates relatives
Chercher dans chaque fichier :
- "hier", "aujourd'hui", "la semaine derniere", "yesterday", "last week"
- Convertir en date absolue ISO (2026-04-06) en utilisant la date de derniere modification du fichier comme ancre

### 2.5 — Verifier les references au code
Pour chaque fichier memoire, extraire les chemins de fichiers cites et verifier avec Glob/Grep :
- Fichier cite existe encore ? Si non, mettre a jour ou supprimer la reference
- Fonction/classe citee existe encore ? Si non, marquer comme potentiellement obsolete

### 2.6 — Supprimer les entrees obsoletes
Criteres de suppression :
- Fichier memoire dont TOUTES les references au code sont cassees
- Information deja presente dans CLAUDE.md ou les fichiers rules/
- Snapshots d'etat (compteurs, scores) de plus de 30 jours sans valeur historique

### 2.7 — Regenerer MEMORY.md
Ecrire un nouvel index avec :
- Categories semantiques (User / Feedback / Project / Reference)
- Une ligne par entree, <150 caracteres
- Total < 200 lignes

## Etape 3 : Verification post-consolidation (mode full)

Relancer le script d'audit. Le verdict DOIT etre CLEAN.
Si ce n'est pas le cas : corriger les problemes restants et relancer.

Afficher le rapport final :
```
=== DREAM COMPLETE ===
Before: X files, Y lines
After:  X files, Y lines
Merged: N files
Removed: N files
Credentials purged: N
Verdict: CLEAN
```

## Regles

1. **Ne JAMAIS supprimer** une memoire de type `feedback` sans confirmation utilisateur
2. **Ne JAMAIS modifier** le contenu semantique — seulement fusionner/reorganiser
3. **Toujours garder** une trace : si un fichier est supprime, son contenu utile est absorbe par un autre
4. **Pas de creation** de nouvelles memoires — consolidation uniquement
5. **Cross-project** : les memoires d'autres repos (ex: lia_scan_context.md) sont consolidables mais pas supprimables
