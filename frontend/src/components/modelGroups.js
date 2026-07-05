// Shared grouping of trained-model sessions: re-training the same algorithm on
// the same dataset creates one session per run, which drowns any raw count or
// list in duplicates. Group by dataset + algo, keep the most recent session,
// and carry a counter of the grouped runs. Used by the Models modal (rows) and
// the header badge (count) so both always agree.

export function groupModels(list) {
  const byKey = new Map();
  for (const s of list || []) {
    const key = (s.filename || '') + '|' + ((s.summary && s.summary.model) || '');
    const cur = byKey.get(key);
    if (!cur) {
      byKey.set(key, { ...s, runs: 1 });
    } else {
      const newer = (s.updated_at || '') > (cur.updated_at || '');
      byKey.set(key, newer ? { ...s, runs: cur.runs + 1 } : { ...cur, runs: cur.runs + 1 });
    }
  }
  return [...byKey.values()].sort((a, b) => (b.updated_at || '').localeCompare(a.updated_at || ''));
}
