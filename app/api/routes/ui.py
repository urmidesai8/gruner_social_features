from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse


router = APIRouter(tags=["ui"])


BASE_DIR = Path(__file__).resolve().parents[2]
STATIC_DIR = BASE_DIR / "static"


@router.get("/")
def ui_home():
    return FileResponse(str(STATIC_DIR / "index.html"))

