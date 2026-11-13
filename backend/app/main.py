from fastapi import FastAPI
from .routers import chat, exercises, studio, terms, tracks, users

app = FastAPI(title="LangLearn")
app.include_router(tracks.router)
app.include_router(users.router)
app.include_router(exercises.router)
app.include_router(chat.router)
app.include_router(studio.router)
app.include_router(terms.router)


@app.get("/health")
def health():
    return {"status": "ok"}
