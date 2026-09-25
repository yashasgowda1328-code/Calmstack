from fastapi import FastAPI
from app.routes import upload, scan

app = FastAPI(
    title="ReConstructAI API",
    description="AI-assisted digital evidence recovery and reconstruction system",
    version="1.0.0"
)

app.include_router(upload.router, prefix="/api", tags=["upload"])
app.include_router(scan.router, prefix="/api", tags=["scan"])


@app.get("/")
def root():
    return {
        "message": "ReConstructAI API is running",
        "status": "online"
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy"
    }