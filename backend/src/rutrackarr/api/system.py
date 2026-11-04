"""System endpoints: health and version."""

from fastapi import APIRouter

from rutrackarr import __version__

router = APIRouter(tags=["system"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/system/status")
async def status() -> dict[str, str]:
    return {"app": "rutrackarr", "version": __version__}
