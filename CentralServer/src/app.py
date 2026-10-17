import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .bootstrap import bootstrap_admin
from .migrations import upgrade_database
from .routers import agents, auth, commands, users


FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "frontend")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    upgrade_database()
    bootstrap_admin()
    yield


app = FastAPI(title="VirtualManager Central Server", version="0.1.0", lifespan=lifespan)
app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIR, "assets")), name="assets")
app.include_router(auth.router)
app.include_router(agents.router)
app.include_router(users.router)
app.include_router(commands.router)


@app.get("/", include_in_schema=False)
def frontend() -> FileResponse:
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))
