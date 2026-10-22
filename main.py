from fastapi import FastAPI
app = FastAPI(title="Whiteboard")
@app.get("/health")
async def health():
    return {"status": "ok"}