# Pre-commit Hooks — PDCA Remediation

Automated quality checks before committing code.

## Hooks

### `pre-commit`
Runs before every commit to enforce:

1. **Python Syntax Check** — All Python files must compile without syntax errors
2. **CLAUDE.md Compliance** — Detects fake patterns:
   - `asyncio.sleep` (fake streaming)
   - `[FALLBACK]` (stub responses)
   - `setTimeout` fakes
   - placeholder patterns
3. **Security** — Prevents accidental secrets in code:
   - API keys
   - Passwords
   - Bearer tokens

## Setup

The hooks are already in place. They will run automatically on `git commit`.

To test manually:

```bash
# Run pre-commit on all staged files
.husky/pre-commit

# Or run git commit (hooks run automatically)
git commit -m "message"
```

## Bypass (Emergency Only)

If you need to bypass hooks:

```bash
git commit --no-verify
```

⚠️ Only use for emergencies. The hooks protect thesis quality.

## Exit Codes

- **0** (green): All checks passed → commit proceeds
- **1** (red): Check failed → commit rejected, fix issue first

## Example Violations

```bash
# ✗ FAIL: asyncio.sleep (fake streaming)
for chunk in response:
    await asyncio.sleep(0.01)  # ← Detected!
    yield chunk

# ✗ FAIL: [FALLBACK] stub
return "[FALLBACK] Response from provider"  # ← Detected!

# ✗ FAIL: API key in code
api_key = "sk-abc123def456"  # ← Detected!

# ✓ PASS: Real streaming
async for token in llm.astream(messages):  # OK
    yield token

# ✓ PASS: Real error handling
raise ValueError("Missing API key")  # OK (no actual key)
```

## History

**Created**: 2026-04-04 (Phase A P2 — Pre-commit hooks)
**Purpose**: Enforce PDCA remediation standards
**Scope**: PromptForge multi-LLM testing interface
