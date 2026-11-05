"""Application assembly. Run: python -m uvicorn app.main:app --reload"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.auth.config import get_settings
from app.database.connection import DatabaseConfigurationError, dispose_engine
from app.routes import auth, counselling, followups, predictions, reports, screenings, students, users
from app.services.errors import RateLimited, ServiceError


@asynccontextmanager
async def lifespan(app):
    yield
    dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Mental Health Screening API", version="1.0.0",
        description="Staff-operated screening support. Model predictions are unavailable.", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins),
        allow_credentials=True, allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"])

    @app.middleware("http")
    async def prevent_sensitive_caching(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(ServiceError)
    async def service_error(request: Request, error: ServiceError):
        headers = {}
        if error.status_code == 401:
            headers["WWW-Authenticate"] = "Bearer"
        if isinstance(error, RateLimited):
            headers["Retry-After"] = str(error.retry_after)
        return JSONResponse(status_code=error.status_code,
            content={"detail":str(error), "code":error.code}, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError):
        # FastAPI's default errors can echo submitted credentials in `input`.
        errors = [{"loc":list(item["loc"]), "msg":item["msg"], "type":item["type"]} for item in error.errors()]
        return JSONResponse(status_code=422, content={"detail":errors})

    @app.exception_handler(DatabaseConfigurationError)
    async def configuration_error(request: Request, error: DatabaseConfigurationError):
        return JSONResponse(status_code=503, content={"detail":"Database configuration is incomplete.", "code":"database_unavailable"})

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, error: SQLAlchemyError):
        return JSONResponse(status_code=503, content={"detail":"Database operation unavailable. Please try again later.", "code":"database_unavailable"})

    @app.get("/", tags=["Health"])
    def home():
        return {"message":"Mental Health Screening API is running"}

    @app.get("/health", tags=["Health"])
    def health():
        return {"status":"healthy"}

    for module in [auth, users, students, screenings, counselling, followups, predictions, reports]:
        app.include_router(module.router)
    return app


app = create_app()
