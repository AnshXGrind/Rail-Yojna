from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI(
    title="Rail-Yojna API",
    version="0.1.0",
    description=(
        "Decision-support API for railway maintenance "
        "risk and planning."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "name": "Rail-Yojna",
        "service": "backend",
        "version": "0.1.0",
    }


# Import routers after app creation to avoid circular-import initialization
# leaving the FastAPI application only partially wired during module import.
from backend.app.api.event_routes import router as event_router
from backend.app.api.inference_routes import router as inference_router
from backend.app.api.report_routes import router as report_router
from backend.app.api.routes import router
from backend.app.api.system_routes import router as system_router


app.include_router(inference_router)
app.include_router(system_router)
app.include_router(report_router)
app.include_router(event_router)
app.include_router(router)
