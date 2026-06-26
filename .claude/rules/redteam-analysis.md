# Regles d'analyse Red Team — AEGIS (ENS, 2026)
# Pour les agents CYBERSEC et WHITEHACKER

## CLASSIFICATION DU VECTEUR D'ATTAQUE — AVANT TOUTE ANALYSE

Chaque papier d'attaque DOIT etre classe dans la taxonomie prompt injection :

| Type | Surface | Exemple |
|------|---------|---------|
| Direct PI (DPI) | Dialogue utilisateur → modele | "Ignore tes instructions et fais X" |
| Indirect PI (IPI) | Donnees tierces (RAG, web, email, API) | Document empoisonne dans le contexte RAG |
| Jailbreak | Guardrails de securite du modele | Contourner RLHF pour obtenir du contenu interdit |
| Goal Hijacking | Actions d'un agent | Rediriger un agent vers un objectif attaquant |
| Prompt Leaking | System prompt confidentiel | Extraire les instructions, cles API, architecture |
| Agent & Multi-step PI | Pipeline multi-agents | Injection dans une etape qui se propage aux suivantes |

**Referentiels obligatoires** :
- MITRE ATLAS AML.T0051 (LLM Prompt Injection)
- OWASP Top 10 for LLM 2025 (LLM01 a LLM10)
- Greshake et al. (2023) arXiv:2302.12173 — fondateur IPI
- Perez & Ribeiro (2022) arXiv:2211.09527 — fondateur DPI

## ANALYSE DU THREAT MODEL — OBLIGATOIRE

Un resultat d'attaque sans threat model precis n'est PAS evaluable.

### Grille obligatoire pour chaque papier

| Composante | Question | Signaux d'alerte |
|-----------|----------|-----------------|
| Capacites attaquant | White-box ou black-box ? Multi-turn ? Acces RAG/outils/memoire ? | Attaquant omniscient = irrealiste |
| Modele cible | Version EXACTE (GPT-4-0613 vs GPT-4-turbo-2024-04-09) | Un seul modele sans justification |
| Objectif | Exfiltration / execution / contournement / manipulation ? | Objectif vague = resultat vague |
| Environnement | Chatbot direct / agent avec outils / pipeline RAG / orchestrateur ? | Surface non specifiee = non evaluable |

## EVALUATION DE L'ASR — METRIQUE CENTRALE ET MANIPULABLE

### Checklist critique obligatoire

1. **Qui juge ?** Juge LLM (manipulable — P044 montre 99% flip rate), evaluation humaine (fiable mais non scalable), regle deterministe (reproductible)
2. **N prompts ?** 10 prompts manuels (anecdotique) vs 1000 automatises (statistiquement valide)
3. **Baseline ?** Comparaison avec GCG, PAIR, AutoDAN, many-shot ? Sans baseline = pas de positionnement
4. **Transfert ?** Cross-modele ? Cross-temporel ? Un ASR de mars 2024 peut etre 0% en decembre 2024
5. **Cout ?** Nombre de requetes, cout API, temps de calcul. Un ASR de 99% qui necessite 10000 requetes est inutilisable

### Metriques complementaires

- FPR cote defense (impact sur utilite normale)
- Cout de l'attaque (requetes, API, GPU)
- Persistance multi-tour
- Transferabilite cross-modele

## REPRODUCTIBILITE & INTEGRATION AEGIS

### Checklist reproductibilite

| Question | Critique | Impact |
|----------|---------|--------|
| Prompts publies ? | OUI/NON/PARTIEL | Sans payload = pas de test AEGIS |
| Modele accessible ? | API publique / open-weight / ferme | Ferme = non reproductible |
| Temperature specifiee ? | temp=0 vs temp=1 = resultats differents | Obligatoire pour reproduction |
| Code/framework fourni ? | URL GitHub | Accelere l'integration |
| ASR encore valide ? | Modeles mis a jour silencieusement | Retester avant d'integrer |

### Protocole d'integration AEGIS (4 etapes)

1. **Extraction payloads** : extraire les prompts de l'article (corps, annexes, GitHub). Categoriser selon taxonomie AEGIS (DPI/IPI/jailbreak/leaking/agent)
2. **Test sur modeles cibles** : reproduire sur LLaMA 3.2 via Ollama + modeles AEGIS. Mesurer ASR avec juge deterministe (PAS LLM-juge)
3. **Test defenses** : si defense proposee, implementer dans AEGIS et mesurer bypass avec la forge existante
4. **Variantes** : generer paraphrases, encodages alternatifs, langues differentes, multi-turn pour enrichir la base

## TEMPLATE FICHE CYBERSEC/WHITEHACKER

```markdown
## [Auteurs, Annee] — Titre

**Reference** : arXiv:XXXX.XXXXX / DOI:XX.XXXX
**Venue** : [Conference/Journal, CORE Ranking]
> **PDF Source**: [literature_for_rag/PXXX_xxx.pdf](../../literature_for_rag/PXXX_xxx.pdf)
> **Statut**: [ARTICLE VERIFIE]

### Classification AEGIS
- **Type d'attaque** : [DPI / IPI / Jailbreak / Leaking / Goal Hijack / Agent PI]
- **Surface ciblee** : [System prompt / Contexte user / Outil / RAG / Agent / Memoire]
- **Modeles testes** : [GPT-4-XXXX / Claude-3.X / LLaMA-X / Mistral-X] + versions exactes
- **Defense evaluee** : [Prompt hardening / Instruction hierarchy / Detection / Sanitization / Aucune]
- **MITRE ATLAS** : [AML.T0051.XXX]
- **OWASP LLM** : [LLM01-LLM10]

### Threat Model
| Composante | Valeur |
|-----------|--------|
| Capacites attaquant | [white-box / black-box / grey-box] |
| Acces | [prompt direct / RAG / outil / memoire] |
| Multi-turn | [oui / non] |
| Objectif | [exfiltration / execution / contournement / manipulation] |

### Resume operationnel (5 lignes)
- **Vecteur** : [description precise]
- **Mecanisme** : [pourquoi le modele obeit] (Section X, p. XX)
- **ASR** : [X% sur N prompts] (Table Y, p. XX)
- **Juge** : [LLM / humain / deterministe]
- **Limite principale** : [...] (Section Limitations, p. XX)

### Analyse critique avec references inline
**Forces** : [...] (Section X, Table Y)
**Faiblesses** : [...] (Section Z, Figure W)
**Transfert cross-modele** : [oui/non, quels modeles] (Section X)
**Temporalite** : [ASR encore valide ? date du test]

### Integration AEGIS
- **Payload extractible** : [oui/non — si oui, reference annexe/GitHub]
- **Mapping templates AEGIS** : [#01-#97 — lesquels correspondent]
- **Mapping chaines AEGIS** : [quelles chaines d'attaque]
- **Defense testable** : [quelle technique de la taxonomie 87]
- **Priorite** : [critique / haute / moyenne / basse] + justification
```

## VEILLE SPECIFIQUE PROMPT INJECTION

### Sources prioritaires

| Source | Frequence | URL |
|--------|-----------|-----|
| arXiv cs.CR + cs.AI | Hebdomadaire | arxiv.org/search/?query=prompt+injection+LLM |
| OWASP LLM Top 10 | Annuelle | owasp.org |
| MITRE ATLAS | Trimestrielle | atlas.mitre.org |
| Simon Willison | Quotidienne | simonwillison.net |
| Lakera AI Blog | Mensuelle | lakera.ai/blog |
| AI Village (DEF CON) | Annuelle | aivillage.org |

### Specificites du domaine

1. **Demi-vie** : un jailbreak fonctionne quelques semaines avant patch silencieux
2. **Pas de CVE** : les corrections RLHF ne sont pas annoncees ni versionnees
3. **Frontiere floue** : instruction-following = le meme mecanisme qui fonctionne et qui est vulnerable
4. **Incidents sous-rapportes** : consulter AI Incident Database + bug bounty (HackerOne, Bugcrowd)
5. **Versioning AEGIS** : chaque vecteur a une date de derniere validation, pas seulement d'integration
