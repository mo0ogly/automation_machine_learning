// file_size_check.cjs — PreToolUse hook for Edit/Write
// Enforces the 800-line rule from .claude/rules/programming.md
// Returns exit 2 to block (file would exceed 800 lines after edit), exit 0 to allow.
//
// Triggered by: Claude Code PreToolUse on Edit, Write, NotebookEdit
// Strategy:
//   - Write: count lines in new_string (the full file content being written)
//   - Edit: estimate post-edit line count (current_lines - old_lines + new_lines)
//   - NotebookEdit: not enforced (notebooks have their own structure)

const fs = require('fs');
const path = require('path');

const MAX_LINES = 800;
const WARN_LINES = 700;

// Files exempt from the rule. Matched against the normalized path
// (forward slashes, no leading separator).
const EXEMPT_PATTERNS = [
  // Generated files
  /(^|\/)(dist|build|out|node_modules|\.next|\.nuxt)\//,
  /(^|\/)package-lock\.json$/,
  /(^|\/)yarn\.lock$/,
  /(^|\/)pnpm-lock\.yaml$/,

  // Datasets and binary-like files
  /(^|\/)chroma_db\//,
  /(^|\/)\.git\//,
  /(^|\/)logs\//,
  // Campaign manifest: growing historical dataset (not code), exempt per programming.md rule
  /(^|\/)research_archive\/experiments\/campaign_manifest\.json$/,

  // Thesis manuscript (explicit exception per programming.md)
  /(^|\/)research_archive\/manuscript\//,

  // The hook itself and CLAUDE.md (rules can be long)
  /(^|\/)\.claude\/hooks\//,
  /(^|\/)CLAUDE\.md$/,

  // Migration / fixture files
  /\.fixture\./,
  /\.snapshot\./,
  /\.generated\./,
];

function isExempt(filePath) {
  // Normalize: backslash → forward slash, strip leading ./
  const normalized = filePath.replace(/\\/g, '/').replace(/^\.\//, '');
  return EXEMPT_PATTERNS.some((re) => re.test(normalized));
}

function countLines(text) {
  if (!text) return 0;
  // Count newlines + 1 if last line has no trailing newline
  const lines = text.split('\n');
  // If the string ends with \n, the split produces an extra empty element
  if (text.endsWith('\n')) return lines.length - 1;
  return lines.length;
}

function readFileLines(filePath) {
  try {
    const content = fs.readFileSync(filePath, 'utf8');
    return countLines(content);
  } catch (_) {
    return 0; // file does not exist yet
  }
}

const chunks = [];
process.stdin.on('data', (c) => chunks.push(c));
process.stdin.on('end', () => {
  const raw = Buffer.concat(chunks).toString('utf8');
  let input = {};
  try {
    input = raw ? JSON.parse(raw) : {};
  } catch (_) {
    process.exit(0);
    return;
  }

  const toolName = input.tool_name || '';
  const toolInput = input.tool_input || {};

  // Only check Write and Edit
  if (toolName !== 'Write' && toolName !== 'Edit') {
    process.exit(0);
    return;
  }

  const filePath = toolInput.file_path || '';
  if (!filePath) {
    process.exit(0);
    return;
  }

  // Check exemptions
  if (isExempt(filePath)) {
    process.exit(0);
    return;
  }

  let projectedLines = 0;
  let currentLines = 0;
  let isGrowing = true;

  if (toolName === 'Write') {
    // Full file content (Write parameter is `content`)
    const content = toolInput.content || '';
    projectedLines = countLines(content);
    currentLines = readFileLines(filePath);
    isGrowing = projectedLines > currentLines;
  } else if (toolName === 'Edit') {
    // Edit replaces old_string with new_string
    currentLines = readFileLines(filePath);
    if (currentLines === 0) {
      // File does not exist — Edit will fail anyway, let it through
      process.exit(0);
      return;
    }
    const oldLines = countLines(toolInput.old_string || '');
    const newLines = countLines(toolInput.new_string || '');
    projectedLines = currentLines - oldLines + newLines;
    isGrowing = newLines > oldLines;
  }

  // Decision logic:
  //   - If projected > MAX and the edit grows the file → BLOCK
  //   - If projected > MAX but the edit shrinks/keeps the file → ALLOW (user is fixing)
  //   - If projected > WARN → warn but allow
  //   - Otherwise → silent allow
  if (projectedLines > MAX_LINES && isGrowing) {
    const msg =
      'FILE SIZE GUARD: ' +
      path.basename(filePath) +
      ' would have ' +
      projectedLines +
      ' lines (limit: ' +
      MAX_LINES +
      ').\n' +
      'Current: ' +
      currentLines +
      ' lines.\n\n' +
      'Per .claude/rules/programming.md, no source file may exceed 800 lines.\n' +
      'Decompose into smaller modules by responsibility:\n' +
      '  - .jsx/.tsx: extract sub-components, hooks, constants\n' +
      '  - .py:       extract classes, helpers, schemas\n' +
      '  - .md:       split by section with an index file\n\n' +
      'If this file MUST exceed 800 lines (rare), add a regex pattern to\n' +
      'EXEMPT_PATTERNS in .claude/hooks/file_size_check.cjs and document why.';
    process.stderr.write(msg);
    process.exit(2);
  }

  if (projectedLines > WARN_LINES) {
    // Warn but allow
    const msg =
      'FILE SIZE WARNING: ' +
      path.basename(filePath) +
      ' will have ' +
      projectedLines +
      ' lines (' +
      MAX_LINES +
      ' max).\n' +
      'Plan its decomposition before it grows further.';
    process.stdout.write(msg);
    process.exit(0);
  }

  process.exit(0);
});
