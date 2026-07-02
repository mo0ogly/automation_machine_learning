// scan_fr.mjs — repere les chaines francaises codees en dur dans le frontend.
// Usage : node .claude/skills/i18n/scripts/scan_fr.mjs frontend/src
//
// Heuristique : texte de noeud JSX et attributs UI (placeholder/title/aria-label/alt)
// contenant un accent FR ou un mot-outil FR frequent. Ignore les fichiers de locale,
// les imports, et les chaines purement techniques. C'est un indicateur, pas un oracle
// parfait : il sert de liste de travail et de test de fin (0 = termine).

import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, extname, sep } from 'node:path';

const root = process.argv[2] || 'frontend/src';

const FR_ACCENTS = /[àâäçéèêëîïôöùûüÿœ]/i;
const FR_WORDS = /\b(le|la|les|un|une|des|du|de|et|ou|avec|sans|pour|dans|sur|par|est|sont|pas|plus|moins|selon|entre|vers|chaque|aucun|aucune|toutes|tous|ceci|cela|votre|vos|cette|ces|afin|donc|ainsi|reglages|reglage|donnees|modele|apercu|enregistrer|annuler|fermer|charger|lancer|verifier|resultat|erreur|succes)\b/i;

// Attributs dont la valeur est affichee a l'utilisateur.
const UI_ATTR = /\b(placeholder|title|aria-label|alt|label)\s*=\s*"([^"]{2,})"/g;
// Texte entre deux balises JSX : >texte<
const JSX_TEXT = />\s*([^<>{}\n][^<>{}]*?)\s*</g;

function looksFrench(s) {
  const t = s.trim();
  if (t.length < 2) return false;
  if (/^[\d\s.,:%/+*\-_=()#{}[\]]+$/.test(t)) return false;   // purement symbolique/numerique
  if (/^[A-Z0-9_]+$/.test(t)) return false;                    // CONSTANTE technique
  if (/^\{.*\}$/.test(t)) return false;                        // expression JSX
  if (/^(https?:|\/|\.|import|export)/.test(t)) return false;  // chemins / urls
  return FR_ACCENTS.test(t) || FR_WORDS.test(t);
}

function scanFile(path) {
  const src = readFileSync(path, 'utf8');
  const lines = src.split('\n');
  const hits = [];
  lines.forEach((line, i) => {
    if (/^\s*(\/\/|\*|import\s|export\s)/.test(line)) return;   // commentaire / import
    let m;
    UI_ATTR.lastIndex = 0;
    while ((m = UI_ATTR.exec(line))) {
      if (looksFrench(m[2])) hits.push({ n: i + 1, kind: 'attr', text: m[2] });
    }
    JSX_TEXT.lastIndex = 0;
    while ((m = JSX_TEXT.exec(line))) {
      if (looksFrench(m[1])) hits.push({ n: i + 1, kind: 'text', text: m[1] });
    }
  });
  return hits;
}

function walk(dir, acc) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    const st = statSync(p);
    if (st.isDirectory()) {
      if (name === 'node_modules' || name === 'locales' || name === 'dist') continue;
      walk(p, acc);
    } else if (['.jsx', '.tsx', '.js', '.ts'].includes(extname(p))) {
      if (p.includes(`${sep}i18n${sep}`)) continue;
      acc.push(p);
    }
  }
  return acc;
}

let total = 0;
for (const file of walk(root, [])) {
  const hits = scanFile(file);
  if (!hits.length) continue;
  console.log(`\n${file}`);
  for (const h of hits) {
    console.log(`  ${h.n}:${h.kind}  ${h.text}`);
    total++;
  }
}
console.log(`\n${total} chaine(s) FR suspecte(s).`);
process.exit(total === 0 ? 0 : 1);
