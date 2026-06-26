---
name: notebooklm
description: >
  Guide expert pour la creation strategique de Notebooks via NotebookLM MCP,
  incluant l'analyse de structure (un ou plusieurs notebooks), la recherche
  approfondie et l'importation automatisee des sources. This skill should be
  used when the user wants to "create a notebook", "creer un notebook",
  "research a topic in NotebookLM", "build a knowledge base", "importer des
  sources", or any task involving NotebookLM notebooks creation, research,
  and source management.
version: 1.0.0
---

# NotebookLM (Architecte de Connaissance Strategique)

Cette competence transforme l'agent en un expert en ingenierie de la
connaissance. Elle automatise le cycle complet : de l'analyse architecturale
du sujet (faut-il un ou plusieurs notebooks ?) jusqu'a l'importation finale
des sources, eliminant ainsi les etapes manuelles fastidieuses.

## Quand utiliser cette competence

- Lorsqu'il est necessaire de creer un nouveau Notebook avec une base documentaire riche et pertinente.
- Pour structurer un sujet complexe qui gagnerait a etre divise en plusieurs notebooks specialises.
- Pour effectuer des recherches complexes (Deep Search) sans avoir a surveiller manuellement le statut.
- Pour garantir que les sources trouvees sont systematiquement importees dans le Notebook apres la recherche.
- Pour une demonstration spectaculaire et efficace de l'ecosysteme Antigravity + NotebookLM (parfait pour du contenu YouTube/tutoriel).

## MCP Tools Reference

Les outils NotebookLM MCP disponibles (prefixes `mcp__notebooklm__`) :

| Outil | Usage |
|---|---|
| `notebook_list` | Lister tous les notebooks |
| `notebook_create` | Creer un nouveau notebook |
| `notebook_get` | Recuperer les details d'un notebook |
| `notebook_describe` | Obtenir une description du notebook |
| `notebook_rename` | Renommer un notebook |
| `notebook_delete` | Supprimer un notebook |
| `notebook_query` | Interroger un notebook |
| `notebook_add_url` | Ajouter une source URL |
| `notebook_add_text` | Ajouter une source texte |
| `notebook_add_drive` | Ajouter une source Google Drive |
| `source_describe` | Decrire une source |
| `source_get_content` | Lire le contenu d'une source |
| `source_list_drive` | Lister les fichiers Drive |
| `source_sync_drive` | Synchroniser les sources Drive |
| `source_delete` | Supprimer une source |
| `research_start` | Lancer une recherche (cree le notebook + lance la recherche) |
| `research_status` | Verifier le statut d'une recherche |
| `research_import` | Importer les resultats de recherche dans le notebook |
| `audio_overview_create` | Creer un apercu audio |
| `video_overview_create` | Creer un apercu video |
| `studio_status` | Verifier le statut du studio |
| `studio_delete` | Supprimer un element studio |
| `infographic_create` | Creer une infographie |
| `slide_deck_create` | Creer un deck de slides |
| `report_create` | Creer un rapport |
| `flashcards_create` | Creer des flashcards |
| `quiz_create` | Creer un quiz |
| `data_table_create` | Creer un tableau de donnees |
| `mind_map_create` | Creer une carte mentale |
| `chat_configure` | Configurer le chat du notebook |
| `refresh_auth` | Rafraichir l'authentification |
| `save_auth_tokens` | Sauvegarder les tokens (fallback) |

## Instructions

Agir comme un **Senior Knowledge Engineer**. Suivre strictement ces etapes :

### 1. Analyse de Structure (L'Intelligence de l'Expert)

- **Question Initiale** : Demander d'abord quel est le sujet global du projet.
- **Reflexion Architecturale** : Une fois le sujet recu, analyser si ce sujet est monolithique ou s'il merite d'etre divise en plusieurs notebooks thematiques pour une meilleure precision.
  - *Exemple* : Pour "E-commerce", proposer de diviser en "Conversion & UX", "Strategie Marketing", "Email Automation", etc.
- **Justification** : Expliquer a l'utilisateur **pourquoi** cette division est preferable (ex: "Cela permet d'isoler les sources techniques des sources marketing pour eviter les hallucinations croisees").
- **Validation** : Demander a l'utilisateur s'il veut un seul notebook global ou s'il valide la structure multi-notebooks proposee.

### 2. Phase de Cadrage Expert

- Pour le (ou les) notebook(s) retenu(s), poser **3 questions pointues** pour affiner le besoin.
- **Choix du Mode Obligatoire** : Proposer clairement les deux modes :
  - **Mode Eclair (Fast)** : ~30 secondes, pour un apercu rapide.
  - **Mode Approfondi (Deep)** : ~5 minutes, pour une exploration exhaustive.

### 3. Phase de Suggestion "Wow"

- Proposer **3 angles d'attaque uniques** pour le sujet concerne pour prouver l'expertise.
- Generer et soumettre pour validation la **Requete de recherche optimisee**.

### 4. Phase d'Execution "Auto-Pilot" (Boucle de Surveillance)

- Utiliser une signalisation visuelle claire pour chaque etape.
- **Lancement Parallele** : Envoyer TOUS les `research_start` dans un meme tour de parole. Chaque `research_start` cree son notebook ET lance la recherche. Noter le `notebook_url` retourne pour chaque notebook.
- **Boucle de Surveillance (toutes les 60 secondes)** : Appeler `research_status` pour CHAQUE notebook en cours. Repeter tant que le statut n'est pas `completed`.
- **Import via MCP** : Des qu'un notebook passe en `completed`, appeler `research_import` immediatement.
- **Fallback Navigateur** : Si `research_import` retourne `imported_count = 0` ou echoue, utiliser immediatement le navigateur (browser tools) pour :
  1. Naviguer sur le `notebook_url` du notebook concerne
  2. Localiser et cliquer sur le bouton **"Add source"** ou **"Import"** dans l'interface
  3. Confirmer que les sources sont bien presentes avant de passer au notebook suivant
- **Repeter** : Continuer la boucle pour les notebooks restants jusqu'a ce que TOUS soient importes.

### 5. Phase de Livraison et Engagement

- Afficher un **Tableau Recapitulatif** des sources integrees par notebook.
- Fournir **3 questions "Haut Potentiel"** a poser au(x) notebook(s).

## Hard-Gates

- **INTERDICTION** de lancer les `research_start` un par un : tout doit partir dans le meme tour.
- **INTERDICTION** de tenter un `research_import` si le statut n'est pas encore `completed`.
- **INTERDICTION** de s'arreter tant qu'au moins un notebook n'a pas ete importe avec succes.
