from fastapi import FastAPI

from app.config import settings

app = FastAPI(title=settings.app_name)


@app.get("/")
def hello():
    return {"message": "Hello from PlanChat"}


# Simple health check, used later by Docker / Render to see if the app is alive.
@app.get("/health")
def health():
    return {"status": "ok"}
