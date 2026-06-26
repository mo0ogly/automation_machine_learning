"""
routes_prompts.py — read/edit the agent's AI prompts (the "Prompts IA" panel).

Exposes the prompt catalog (system instructions + per-stage few-shot examples)
with each prompt's default value, current value, override flag, and its UI
*localisation* (where it is used in the front). Edits are persisted as overrides
in ``prompt_store`` and picked up on the next agent call (hot reload).
"""

from fastapi import APIRouter, Body, HTTPException

import agent_prompts
import prompt_store

router = APIRouter(prefix="/api/prompts", tags=["prompts"])


def _entry(prompt_id: str) -> dict:
    return next((e for e in agent_prompts.catalog() if e["id"] == prompt_id), None)


@router.get("")
def list_prompts():
    """Full catalog: id, kind, label, description, localisation, default, value, overridden."""
    return {"prompts": agent_prompts.catalog()}


@router.put("/{prompt_id}")
def set_prompt(prompt_id: str, body: dict = Body(default={})):
    """Override a prompt. Text prompts expect a non-empty string ``value``;
    few-shot (json) prompts expect an object/array ``value``."""
    if not agent_prompts.is_valid_id(prompt_id):
        raise HTTPException(status_code=404, detail="Prompt inconnu.")
    value = body.get("value")
    kind = agent_prompts.kind_of(prompt_id)
    if kind == "text":
        if not isinstance(value, str) or not value.strip():
            raise HTTPException(status_code=400, detail="Le prompt texte ne peut pas être vide.")
    elif kind == "json":
        if not isinstance(value, (dict, list)):
            raise HTTPException(status_code=400, detail="Le few-shot doit être un objet ou un tableau JSON.")
    prompt_store.STORE.set(prompt_id, value)
    return _entry(prompt_id)


@router.delete("/{prompt_id}")
def reset_prompt(prompt_id: str):
    """Drop the override and fall back to the default value."""
    if not agent_prompts.is_valid_id(prompt_id):
        raise HTTPException(status_code=404, detail="Prompt inconnu.")
    prompt_store.STORE.reset(prompt_id)
    return _entry(prompt_id)
