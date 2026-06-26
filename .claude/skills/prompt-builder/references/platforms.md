# Platform-Specific Prompt Patterns

Reference des structures et syntaxes validees par plateforme. Mise a jour : 2026-03.

## Claude (Anthropic)

**Structure optimale :**
```xml
<context>
{contexte du domaine, donnees, contraintes}
</context>

<instructions>
{instructions precises, etape par etape}
</instructions>

<output_format>
{format attendu : JSON, markdown, code, etc.}
</output_format>

<examples>
<example>
<input>{entree}</input>
<output>{sortie attendue}</output>
</example>
</examples>

<constraints>
{ce qu'il ne doit PAS faire, limites, garde-fous}
</constraints>
```

**Bonnes pratiques :**
- Balises XML pour structurer les sections (Claude les parse nativement)
- System prompt pour le role et les contraintes durables
- Few-shot examples dans des balises `<example>`
- Chain-of-thought : demander de "reflechir etape par etape" ou utiliser `<thinking>` tags
- Prefilling : commencer la reponse assistant pour guider le format
- Etre direct : pas de formules de politesse, aller droit au but
- Long context : mettre les donnees longues en DEBUT de prompt, instructions a la FIN

**Anti-patterns :**
- "Tu es un assistant utile" (deja le comportement par defaut)
- Instructions contradictoires entre system et user
- Prompts trop courts sans contexte (Claude sous-performe)
- Instructions agressives en majuscules ("CRITICAL!", "YOU MUST", "NEVER EVER") — les modeles Claude 4.x repondent mieux a des instructions calmes et motivees
- Claude 4.x est litteraliste : il fait exactement ce qui est demande, pas plus

---

## GPT-4 / ChatGPT (OpenAI)

**Structure optimale :**
```
System: {role + contraintes + format}
User: {tache + contexte + exemples}
Assistant: {prefill optionnel}
```

**Bonnes pratiques :**
- System message pour le persona, les regles, le format de sortie
- Delimiter les sections avec `###` ou `---` ou `"""`
- Few-shot : alterner User/Assistant messages
- JSON mode : ajouter `"response_format": {"type": "json_object"}` dans l'API
- Chain-of-thought : "Let's think step by step"
- Temperature : 0-0.3 pour factuel, 0.7-1.0 pour creatif

**Anti-patterns :**
- System prompt trop long (>2000 tokens degrade la qualite)
- Melanger plusieurs taches dans un seul prompt
- "Don't hallucinate" (inefficace, preferer "If unsure, say 'I don't know'")

---

## Midjourney

**Structure optimale :**
```
{sujet principal}, {details visuels}, {style/medium}, {eclairage}, {composition} --ar {ratio} --v {version} --s {stylize} --q {quality}
```

**Parametres principaux :**
- `--ar 16:9` / `--ar 1:1` / `--ar 9:16` : ratio d'aspect
- `--v 7` : version du modele (defaut actuel 2026)
- `--s 0-1000` : stylisation
- `--q .25 / .5 / 1` : qualite
- `--no {element}` : exclusion negative
- `--sref {URL|code}` : Style Reference
- `--cref {URL}` : Character Reference

**Note :** Lancer un WebSearch "Midjourney latest version parameters {year}" pour confirmer les params courants.

---

## Stable Diffusion (SDXL / SD3 / Flux)

**Structure positive :**
```
{sujet}, {description detaillee}, {style}, {qualite}
```

**Syntaxe poids :**
- `(mot:1.4)` : augmenter l'importance
- `(mot:0.6)` : reduire l'importance

**Bonnes pratiques :**
- Negative prompt : "blurry, low quality, deformed, extra limbs, watermark"
- CFG Scale : 7-12
- Steps : 20-30 pour SDXL
- Sampler : DPM++ 2M Karras

---

## Cursor / Windsurf / Bolt (AI Code Editors)

**Structure optimale :**
```
## Context
{description du projet, stack, fichiers concernes}

## Task
{tache precise avec criteres d'acceptation}

## Constraints
- {convention de nommage}
- {patterns existants a respecter}
```

---

## LLMs Locaux (Ollama, LM Studio, vLLM)

**Bonnes pratiques :**
- Prompts plus explicites (modeles plus petits = moins d'inference)
- System prompt court (<500 tokens pour 7B)
- Format de chat : respecter le template du modele (ChatML, Llama, etc.)
- Eviter les instructions complexes multi-etapes (decomposer)
- Temperature 0 pour les taches deterministes
- Repeter les contraintes critiques (les petits modeles oublient)
- Anti-pattern ABSOLU : CAPS agressifs ("SYSTEM OVERRIDE", "YOU MUST") — les modeles alignes y resistent mieux que les prompts calmes et autorises

---

## Gemini (Google)

**Bonnes pratiques :**
- Grounding avec Google Search pour les faits recents
- System instructions : role + contraintes
- Long context (1M+ tokens) : instructions a la fin

---

## Perplexity

**Bonnes pratiques :**
- Focus modes : Academic, Writing, Math
- Demander les sources explicitement
- Pro Search pour questions complexes multi-etapes
