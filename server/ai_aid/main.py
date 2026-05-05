from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="ai-aid", version="0.1.0")
    return app
