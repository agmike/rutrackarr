"""Overrides page: list, save, delete, export and import (JSON)."""

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from rutrackarr.torznab.overrides import OverrideError, from_json

router = APIRouter(prefix="/overrides", tags=["overrides"])


@router.get("")
def list_overrides(request: Request) -> dict[str, Any]:
    return {"items": [o.to_json() for o in request.app.state.overrides.all()]}


@router.post("")
def save_override(request: Request, body: dict[str, Any]) -> dict[str, Any]:
    """Create or replace the override for (kind, external_id)."""
    try:
        o = from_json(body)
    except OverrideError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    return request.app.state.overrides.save(o).to_json()  # type: ignore[no-any-return]


@router.delete("/{override_id}")
def delete_override(override_id: int, request: Request) -> dict[str, bool]:
    if not request.app.state.overrides.delete(override_id):
        raise HTTPException(status_code=404, detail="No such override")
    return {"ok": True}


@router.get("/export")
def export_overrides(request: Request) -> dict[str, Any]:
    items = []
    for o in request.app.state.overrides.all():
        d = o.to_json()
        d.pop("id", None)
        d.pop("updated_at", None)
        items.append(d)
    return {"rutrackarr_overrides": 1, "items": items}


@router.post("/import")
def import_overrides(request: Request, body: dict[str, Any]) -> dict[str, Any]:
    """Each item replaces the override of the same series/film; others are kept. All items are
    checked before any is saved."""
    items = body.get("items")
    if not isinstance(items, list):
        raise HTTPException(status_code=422, detail='Expected {"items": [...]}')
    try:
        parsed = [from_json(d) for d in items]
    except OverrideError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    for o in parsed:
        request.app.state.overrides.save(o)
    return {"imported": len(parsed)}
