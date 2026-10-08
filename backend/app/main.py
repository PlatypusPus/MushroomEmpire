from fastapi import FastAPI

from app.api import router

app = FastAPI(title="CoastGuard AI")
app.include_router(router, prefix="/api")
