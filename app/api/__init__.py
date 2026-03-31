from fastapi import FastAPI


def include_routers(app: FastAPI) -> None:
    """
    Attach all API and UI routers to the main FastAPI application.
    Routers are defined in app.api.routes.*.
    """
    from app.api.routes import image, video, text, ui

    app.include_router(image.router)
    app.include_router(video.router)
    app.include_router(text.router)
    app.include_router(ui.router)

