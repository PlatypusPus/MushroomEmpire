from fastapi import FastAPI

from app.api import router, ws_router

app = FastAPI(title="KADAL")
app.include_router(router, prefix="/api")
app.include_router(ws_router)
