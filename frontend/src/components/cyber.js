// Shared "is this a cyber dataset?" heuristic, used to highlight cyber models /
// datasets / sessions across the UI (Models menu + landing). Detection is by
// keyword in the dataset name — adjust the list here and every view follows.

export const CYBER_KEYWORDS = [
  'cyber', 'prompt', 'injection', 'fraud', 'malware', 'phishing',
  'intrusion', 'threat', 'attack', 'exploit', 'vuln', 'anomal', 'transaction',
];

export function isCyber(name) {
  const n = (name || '').toLowerCase();
  return CYBER_KEYWORDS.some((k) => n.includes(k));
}
