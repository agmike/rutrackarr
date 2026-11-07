"""System endpoints: health and version."""

from fastapi import APIRouter

from rutrackarr import REPOSITORY, __commit__, __version__

router = APIRouter(tags=["system"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/system/status")
async def status() -> dict[str, str | None]:
    return {
        "app": "RuTrackarr",
        "version": __version__,
        "commit": __commit__,
        "repository": REPOSITORY,
    }
