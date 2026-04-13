from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import include_routers


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"


def create_app() -> FastAPI:
    app = FastAPI(title="Gruner Social AI Features")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _request: Request,
        _exc: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"detail": "Bad request — request body validation failed."},
        )

    def custom_openapi() -> dict:
        if app.openapi_schema:
            return app.openapi_schema

        schema = get_openapi(
            title=app.title,
            version="1.0.0",
            description=app.description,
            routes=app.routes,
        )

        paths = schema.get("paths", {})
        for path_key, path_item in paths.items():
            for method, operation in path_item.items():
                if method.startswith("x-") or not isinstance(operation, dict):
                    continue
                responses = operation.get("responses", {})
                if not isinstance(responses, dict):
                    responses = {}
                    operation["responses"] = responses

                # Drop FastAPI default validation schema; real validation maps to 400 at runtime.
                responses.pop("422", None)

                # Description-only entries (no media type / example) — prod-style docs.
                responses["400"] = {
                    "description": (
                        "Bad request — invalid or missing input, or request body validation failure."
                    ),
                }
                responses["500"] = {
                    "description": (
                        "Internal server error — upstream provider failure or unexpected error."
                    ),
                }

                # Static UI: file may be missing on disk in misconfigured deployments.
                if path_key == "/" and method.lower() == "get":
                    responses["404"] = {
                        "description": "Not found — UI asset unavailable.",
                    }

        app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = custom_openapi

    include_routers(app)

    @app.get("/api/ping")
    async def ping() -> dict:
        return {"status": "ok"}

    return app


app = create_app()

