from fastapi import FastAPI

app = FastAPI(title="MovieBot API")


@app.get("/health")
async def health():
    """Health check — verifica que la infraestructura HTTP funciona."""
    return {"status": "ok"}
