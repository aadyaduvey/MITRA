"""FastAPI app entry. Routers are wired in M3."""
from fastapi import FastAPI

app = FastAPI(title="MITRA", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
