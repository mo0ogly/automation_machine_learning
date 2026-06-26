#!/usr/bin/env node
// auto_wiki_rebuild_worker.cjs — standalone worker invoked by auto_wiki_rebuild.cjs
//
// This process is spawned detached and survives the parent hook's process.exit(0).
// It runs the full rebuild pipeline sequentially and logs every step, so the
// post-build `mkdocs build` chain does not rely on Node event-loop callbacks
// that die with the parent.
//
// Invocation (synchronous, spawned detached):
//   node auto_wiki_rebuild_worker.cjs <triggered_by_path>
//
// This worker:
//   1. Runs `python build_wiki.py` in wiki/
//   2. If that succeeds, runs `python -m mkdocs build` in wiki/
//   3. Logs every step to .claude/logs/wiki_rebuild.log
//   4. Clears the .wiki_rebuild_pending marker on success
//
// The worker exits on its own schedule. The invoking hook does NOT wait.

const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const MARKER_FILE = path.join(REPO_ROOT, '.claude', '.wiki_rebuild_pending');
const LOG_DIR = path.join(REPO_ROOT, '.claude', 'logs');
const LOG_FILE = path.join(LOG_DIR, 'wiki_rebuild.log');

const triggeredBy = process.argv[2] || 'unknown';

function logLine(msg) {
  try {
    if (!fs.existsSync(LOG_DIR)) fs.mkdirSync(LOG_DIR, { recursive: true });
    const ts = new Date().toISOString();
    fs.appendFileSync(LOG_FILE, `[${ts}] [worker] ${msg}\n`, 'utf8');
  } catch (e) { /* ignore */ }
}

function clearMarker() {
  try {
    if (fs.existsSync(MARKER_FILE)) fs.unlinkSync(MARKER_FILE);
  } catch (e) { /* ignore */ }
}

logLine(`Worker started for ${triggeredBy}`);

const isWin = process.platform === 'win32';
const pythonBin = isWin ? 'python.exe' : 'python3';
const wikiDir = path.join(REPO_ROOT, 'wiki');

// Step 1: build_wiki.py
logLine(`Running build_wiki.py in ${wikiDir}...`);
const buildResult = spawnSync(
  pythonBin,
  ['build_wiki.py'],
  {
    cwd: wikiDir,
    encoding: 'utf8',
    timeout: 120_000, // 2 min
    windowsHide: true,
  },
);

if (buildResult.error) {
  logLine(`build_wiki.py SPAWN ERROR: ${buildResult.error.message}`);
  process.exit(2);
}
if (buildResult.status !== 0) {
  logLine(`build_wiki.py FAIL (exit ${buildResult.status}): ${(buildResult.stderr || '').slice(0, 500)}`);
  process.exit(2);
}
logLine(`build_wiki.py OK (exit 0)`);

// Step 2: mkdocs build
logLine(`Running mkdocs build in ${wikiDir}...`);
const mkdocsResult = spawnSync(
  pythonBin,
  ['-m', 'mkdocs', 'build'],
  {
    cwd: wikiDir,
    encoding: 'utf8',
    timeout: 180_000, // 3 min
    windowsHide: true,
  },
);

if (mkdocsResult.error) {
  logLine(`mkdocs SPAWN ERROR: ${mkdocsResult.error.message}`);
  process.exit(3);
}
if (mkdocsResult.status !== 0) {
  logLine(`mkdocs build FAIL (exit ${mkdocsResult.status}): ${(mkdocsResult.stderr || '').slice(0, 500)}`);
  process.exit(3);
}

// Parse mkdocs output for page count + warnings
const stdout = mkdocsResult.stdout || '';
const pagesMatch = stdout.match(/Documentation built in ([\d.]+ seconds)/);
const warningCount = (stdout.match(/^WARNING/gm) || []).length;
logLine(
  `mkdocs build OK (exit 0)${pagesMatch ? ' - ' + pagesMatch[1] : ''}${warningCount ? ' - ' + warningCount + ' warnings' : ''}`,
);

clearMarker();
logLine(`Rebuild complete for ${triggeredBy}`);
process.exit(0);
