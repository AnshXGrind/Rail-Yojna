from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.api.inference_routes import router as inference_router
from backend.app.api.routes import router


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

app.include_router(router)
app.include_router(inference_router)


@app.get("/")
def root():
    return {
        "name": "Rail-Yojna",
        "service": "backend",
        "version": "0.1.0",
    }
