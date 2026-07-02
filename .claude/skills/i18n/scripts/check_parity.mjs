// check_parity.mjs — verifie la parite des cles entre locales/fr et locales/en.
// Usage : node .claude/skills/i18n/scripts/check_parity.mjs frontend/src/i18n/locales
//
// Pour chaque namespace present cote fr/, verifie que en/<ns>.json existe et contient
// exactement les memes cles (a plat, notation pointee). Signale les cles manquantes,
// les cles en trop, et les valeurs EN restees identiques au FR (traduction oubliee).

import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { join } from 'node:path';

const root = process.argv[2] || 'frontend/src/i18n/locales';
const frDir = join(root, 'fr');
const enDir = join(root, 'en');

if (!existsSync(frDir) || !existsSync(enDir)) {
  console.error(`Dossiers introuvables : ${frDir} et/ou ${enDir}`);
  process.exit(2);
}

function flatten(obj, prefix, out) {
  for (const [k, v] of Object.entries(obj)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === 'object' && !Array.isArray(v)) flatten(v, key, out);
    else out[key] = v;
  }
  return out;
}

function load(dir, ns) {
  const p = join(dir, ns);
  if (!existsSync(p)) return null;
  return flatten(JSON.parse(readFileSync(p, 'utf8')), '', {});
}

let problems = 0;
for (const ns of readdirSync(frDir).filter((f) => f.endsWith('.json'))) {
  const fr = load(frDir, ns);
  const en = load(enDir, ns);
  if (!en) {
    console.log(`[MANQUANT] en/${ns} absent`);
    problems++;
    continue;
  }
  const frKeys = new Set(Object.keys(fr));
  const enKeys = new Set(Object.keys(en));
  for (const k of frKeys) if (!enKeys.has(k)) { console.log(`[EN manque] ${ns} :: ${k}`); problems++; }
  for (const k of enKeys) if (!frKeys.has(k)) { console.log(`[EN en trop] ${ns} :: ${k}`); problems++; }
  for (const k of frKeys) {
    if (enKeys.has(k) && typeof fr[k] === 'string' && fr[k] === en[k] && /[àâäçéèêëîïôöùûüÿœ]/i.test(fr[k])) {
      console.log(`[non traduit] ${ns} :: ${k}  ("${fr[k]}")`);
      problems++;
    }
  }
}
console.log(`\n${problems} probleme(s) de parite.`);
process.exit(problems === 0 ? 0 : 1);
