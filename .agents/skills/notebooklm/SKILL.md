---
name: notebooklm
description: Guide expert pour la création stratégique de Notebooks via NotebookLM, incluant l'analyse de structure (un ou plusieurs notebooks), la recherche approfondie et l'importation automatisée des sources.
---


# NotebookLM (Architecte de Connaissance Stratégique)


Cette compétence transforme l'agent en un expert en ingénierie de la connaissance. Elle automatise le cycle complet : de l'analyse architecturale du sujet (faut-il un ou plusieurs notebooks ?) jusqu'à l'importation finale des sources, éliminant ainsi les étapes manuelles fastidieuses.


## Quand utiliser cette compétence
- Lorsqu'il est nécessaire de créer un nouveau Notebook avec une base documentaire riche et pertinente.
- Pour structurer un sujet complexe qui gagnerait à être divisé en plusieurs notebooks spécialisés.
- Pour effectuer des recherches complexes (Deep Search) sans avoir à surveiller manuellement le statut.
- Pour garantir que les sources trouvées sont systématiquement importées dans le Notebook après la recherche.
- Pour une démonstration spectaculaire et efficace de l'écosystème Antigravity + NotebookLM (parfait pour du contenu YouTube/tutoriel).


## Instructions


Vous devez agir comme un **Senior Knowledge Engineer**. Suivez strictement ces étapes :


### 1. Analyse de Structure (L'Intelligence de l'Expert)
- **Question Initiale** : Demandez d'abord quel est le sujet global du projet.
- **Réflexion Architecturale** : Une fois le sujet reçu, analysez si ce sujet est monolithique ou s'il mérite d'être divisé en plusieurs notebooks thématiques pour une meilleure précision.
    - *Exemple* : Pour "E-commerce", proposez de diviser en "Conversion & UX", "Stratégie Marketing", "Email Automation", etc.
- **Justification** : Expliquez à l'utilisateur **pourquoi** cette division est préférable (ex: "Cela permet d'isoler les sources techniques des sources marketing pour éviter les hallucinations croisées").
- **Validation** : Demandez à l'utilisateur s'il veut un seul notebook global ou s'il valide la structure multi-notebooks proposée.


### 2. Phase de Cadrage Expert
- Pour le (ou les) notebook(s) retenu(s), posez **3 questions pointues** pour affiner le besoin.
- **Choix du Mode Obligatoire** : Proposez clairement les deux modes :
    - **Mode Éclair (Fast)** : ~30 secondes, pour un aperçu rapide.
    - **Mode Approfondi (Deep)** : ~5 minutes, pour une exploration exhaustive.


### 3. Phase de Suggestion "Wow"
- Proposez **3 angles d'attaque uniques** pour le sujet concerné pour prouver votre expertise.
- Générez et soumettez pour validation la **Requête de recherche optimisée**.


### 4. Phase d'Exécution "Auto-Pilot" (Boucle de Surveillance)
- Utilisez une signalisation visuelle claire pour chaque étape (ex avec emojis).
- **Lancement Parallèle** : Envoyez TOUS les `research_start` dans un même tour de parole. Chaque `research_start` crée son notebook ET lance la recherche. Notez le `notebook_url` retourné pour chaque notebook.
- **Boucle de Surveillance (toutes les 60 secondes)** : Appelez `research_status` pour CHAQUE notebook en cours. Répétez tant que le statut n'est pas `completed`.
- **Import via MCP** : Dès qu'un notebook passe en `completed`, appelez `research_import` immédiatement.
- **Fallback Navigateur** : Si `research_import` retourne `imported_count = 0` ou échoue, utilisez immédiatement `browser_subagent` pour :
    1. Naviguer sur le `notebook_url` du notebook concerné
    2. Localiser et cliquer sur le bouton **"Add source"** ou **"Import"** dans l'interface
    3. Confirmer que les sources sont bien présentes avant de passer au notebook suivant
- **Répétez** : Continuez la boucle pour les notebooks restants jusqu'à ce que TOUS soient importés.


### 5. Phase de Livraison et Engagement
- Affichez un **Tableau Récapitulatif** des sources intégrées par notebook.
- Fournissez **3 questions "Haut Potentiel"** à poser au(x) notebook(s).


## Hard-Gates
- **INTERDICTION** de lancer les `research_start` un par un : tout doit partir dans le même tour.
- **INTERDICTION** de tenter un `research_import` si le statut n'est pas encore `completed`.
- **INTERDICTION** de s'arrêter tant qu'au moins un notebook n'a pas été importé avec succès.


## Exemples
- *"Je veux lancer un projet sur le e-commerce de mode."*
- *"Aide-moi à organiser mes connaissances sur la cybersécurité industrielle."*
