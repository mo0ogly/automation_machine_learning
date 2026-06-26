#!/usr/bin/env python3
"""Checkpoint system for aegis-research-lab apex skill.

Inspired by Agent Laboratory `state_saves/` (arXiv 2501.04227).
Allows an apex session to be suspended and resumed after interruption
(context overflow, crash, manual pause).

Usage:
    python checkpoint.py save SESSION-043 --phase DELEGATE --payload state.json
    python checkpoint.py load SESSION-043
    python checkpoint.py list
    python checkpoint.py prune --older-than 7
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent.parent.parent  # poc_medical/
CHECKPOINT_DIR = ROOT / "_staging" / "research-lab"


def _ensure_dir() -> None:
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)


def _checkpoint_path(session_id: str) -> Path:
    return CHECKPOINT_DIR / f"CHECKPOINT_{session_id}.json"


def save_checkpoint(session_id: str, state: dict) -> Path:
    """Save the apex state for a session. Overwrites the previous checkpoint.

    The state dict should contain at minimum:
      - phase_courante (str)
      - phases_completees (list[str])
      - triage_bacs (dict)
      - delegations_terminees (list[dict])
      - delegations_pending (list[dict])
      - buffer_rapports (dict — can be large)
      - drift_check_last (str)
      - tokens_consumed_estimate (int)
    """
    _ensure_dir()
    state = dict(state)  # copy
    state["session_id"] = session_id
    state["timestamp"] = datetime.now().isoformat()
    state["checkpoint_version"] = 1

    path = _checkpoint_path(session_id)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False, default=str),
                    encoding="utf-8")
    return path


def load_checkpoint(session_id: str) -> dict | None:
    """Return the most recent checkpoint for this session, or None."""
    path = _checkpoint_path(session_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def list_checkpoints() -> list[dict]:
    """Return a list of {session_id, timestamp, phase, mtime_iso} for all checkpoints."""
    _ensure_dir()
    out = []
    for f in sorted(CHECKPOINT_DIR.glob("CHECKPOINT_*.json"),
                    key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            out.append({
                "session_id": data.get("session_id", f.stem),
                "timestamp": data.get("timestamp", "?"),
                "phase_courante": data.get("phase_courante", "?"),
                "phases_completees": data.get("phases_completees", []),
                "delegations_done": len(data.get("delegations_terminees", [])),
                "delegations_pending": len(data.get("delegations_pending", [])),
                "file": f.name,
                "mtime": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
            })
        except (json.JSONDecodeError, OSError) as e:
            out.append({"session_id": f.stem, "error": str(e), "file": f.name})
    return out


def prune_checkpoints(older_than_days: int) -> list[str]:
    """Delete checkpoints older than N days. Returns list of deleted files."""
    _ensure_dir()
    cutoff = datetime.now() - timedelta(days=older_than_days)
    deleted = []
    for f in CHECKPOINT_DIR.glob("CHECKPOINT_*.json"):
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        if mtime < cutoff:
            f.unlink()
            deleted.append(f.name)
    return deleted


def main():
    parser = argparse.ArgumentParser(
        description="Checkpoint system for aegis-research-lab apex sessions"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_save = sub.add_parser("save", help="Save a checkpoint for a session")
    p_save.add_argument("session_id")
    p_save.add_argument("--phase", required=True, help="Current phase (OPEN|TRIAGE|...)")
    p_save.add_argument("--payload", help="Path to a JSON file with the full state")
    p_save.add_argument("--inline", help="Inline JSON state (if no payload file)")

    p_load = sub.add_parser("load", help="Load a checkpoint for a session")
    p_load.add_argument("session_id")
    p_load.add_argument("--summary", action="store_true", help="Show summary only")

    sub.add_parser("list", help="List all checkpoints")

    p_prune = sub.add_parser("prune", help="Delete old checkpoints")
    p_prune.add_argument("--older-than", type=int, default=7,
                         help="Delete checkpoints older than N days (default 7)")

    args = parser.parse_args()

    if args.cmd == "save":
        if args.payload:
            state = json.loads(Path(args.payload).read_text(encoding="utf-8"))
        elif args.inline:
            state = json.loads(args.inline)
        else:
            state = {}
        state["phase_courante"] = args.phase
        path = save_checkpoint(args.session_id, state)
        print(f"Checkpoint saved: {path}")

    elif args.cmd == "load":
        data = load_checkpoint(args.session_id)
        if not data:
            print(f"No checkpoint found for {args.session_id}", file=sys.stderr)
            sys.exit(1)
        if args.summary:
            print(f"Session    : {data.get('session_id')}")
            print(f"Timestamp  : {data.get('timestamp')}")
            print(f"Phase      : {data.get('phase_courante')}")
            print(f"Phases done: {', '.join(data.get('phases_completees', []))}")
            print(f"Delegations: {len(data.get('delegations_terminees', []))} done / "
                  f"{len(data.get('delegations_pending', []))} pending")
        else:
            print(json.dumps(data, indent=2, ensure_ascii=False))

    elif args.cmd == "list":
        checkpoints = list_checkpoints()
        if not checkpoints:
            print("(no checkpoints)")
            return
        for c in checkpoints:
            if "error" in c:
                print(f"  [ERR] {c['file']} — {c['error']}")
                continue
            phases = ",".join(c["phases_completees"]) if c["phases_completees"] else "-"
            print(f"  {c['session_id']:30s}  {c['phase_courante']:12s}  "
                  f"done={c['delegations_done']} pending={c['delegations_pending']}  "
                  f"({c['mtime'][:16]})")

    elif args.cmd == "prune":
        deleted = prune_checkpoints(args.older_than)
        if deleted:
            print(f"Deleted {len(deleted)} checkpoints:")
            for f in deleted:
                print(f"  - {f}")
        else:
            print(f"No checkpoints older than {args.older_than} days.")


if __name__ == "__main__":
    main()
