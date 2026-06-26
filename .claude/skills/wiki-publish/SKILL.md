---
name: wiki-publish
description: "Synchronise et publie le wiki MkDocs du projet AEGIS sur GitHub Pages. Modes: update (incremental), full (rebuild complet), serve (preview local)."
user-invocable: true
---

# /wiki-publish

Skill de maintenance du wiki AEGIS (MkDocs Material sur GitHub Pages).

## Modes

| Mode | Usage | Description |
|------|-------|-------------|
| `update` | `/wiki-publish update` | Build incremental + commit + push |
| `full` | `/wiki-publish full` | Clean + rebuild complet + commit + push |
| `serve` | `/wiki-publish serve` | Preview locale (http://localhost:8000) |
| `check` | `/wiki-publish check` | Build sans deployer, affiche les warnings |

## Procedure

### Mode `update` (defaut) ou `full`

1. **Assembler les sources** :
   ```bash
   cd wiki && python build_wiki.py
   ```

2. **Verifier le build** :
   ```bash
   cd wiki && mkdocs build 2>&1
   ```
   - Si 0 WARNING : continuer
   - Si WARNING : afficher a l'utilisateur, demander confirmation

3. **Verifier les stats** :
   - Nombre de pages generees (attendu : ~109)
   - Nombre d'images copiees (attendu : ~29)
   - Comparer avec le dernier build (detection de regression)

4. **Commit et push** :
   ```bash
   git add wiki/ .github/workflows/deploy.yml
   git commit -m "docs(wiki): update MkDocs wiki — N pages

   Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
   git push
   ```

5. **Verifier le deploiement** :
   - Le workflow GitHub Actions se declenche automatiquement
   - URL finale : `https://pizzif.github.io/poc_medical/wiki/`

### Mode `serve`

1. Assembler les sources : `python build_wiki.py`
2. Lancer le serveur local : `mkdocs serve`
3. Ouvrir http://localhost:8000 pour preview

### Mode `check`

1. Assembler les sources : `python build_wiki.py`
2. Builder : `mkdocs build 2>&1`
3. Compter les warnings et les afficher
4. Ne PAS committer ni pusher

## Fichiers impliques

| Fichier | Role |
|---------|------|
| `wiki/mkdocs.yml` | Configuration MkDocs Material |
| `wiki/build_wiki.py` | Script d'assemblage des sources |
| `wiki/requirements.txt` | Dependencies Python |
| `wiki/docs/index.md` | Page d'accueil (statique) |
| `wiki/docs/installation.md` | Guide d'installation (statique) |
| `wiki/docs/` | Dossier genere par build_wiki.py |
| `wiki/site/` | Site statique genere par mkdocs build |
| `.github/workflows/deploy.yml` | Workflow CI/CD |

## Sources synchronisees

Le script `build_wiki.py` copie depuis :

- `README.md`, `AI_SYSTEM.md`, `ROADMAP.md` (racine)
- `backend/README.md`
- `docs/` (Mermaid, Red Team Lab, plans)
- `figures/` (images)
- `research_archive/doc_references/` (80 papiers, glossaire, manifest)
- `research_archive/discoveries/` (conjectures, gaps, decouvertes)
- `research_archive/articles/` (articles de recherche)
- `research_archive/_staging/` (resume des agents)
- `research_archive/RESEARCH_STATE.md`, `RESEARCH_ARCHIVE_GUIDE.md`

## Regles

1. **Ne jamais editer directement dans `wiki/docs/`** sauf `index.md` et `installation.md` — tout le reste est genere par `build_wiki.py`
2. **`wiki/site/` est dans .gitignore** — ne jamais committer le build
3. **Les PDFs ne sont pas inclus** — les liens vers `literature_for_rag/` sont neutralises en `code` inline
4. **Les images > 1MB sont exclues** (`full_demo_v3.webp`)
