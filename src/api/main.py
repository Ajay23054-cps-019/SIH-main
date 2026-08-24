"""SAT-SA API entry point."""
from fastapi import FastAPI

app = FastAPI(
    title="SAT-SA",
    description="Supervisory Analytics Tool for SOC Assessment (SIH26157, NCIIPC)",
    version="0.1.0",
)


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}
