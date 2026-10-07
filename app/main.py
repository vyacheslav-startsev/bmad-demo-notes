from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import db

BASE = Path(__file__).parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="Заметки", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")


def clean(title: str, body: str) -> tuple[str, str]:
    title = title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Заголовок не может быть пустым")
    return title, body.strip()


@app.get("/", response_class=HTMLResponse)
def index(request: Request, q: str = ""):
    q = q.strip()
    notes = db.search_notes(q) if q else db.list_notes()
    return templates.TemplateResponse(
        request, "index.html", {"notes": notes, "q": q}
    )


@app.post("/notes")
def create(title: str = Form(...), body: str = Form("")):
    title, body = clean(title, body)
    db.create_note(title, body)
    return RedirectResponse("/", status_code=303)


@app.get("/notes/{note_id}", response_class=HTMLResponse)
def edit(request: Request, note_id: int):
    note = db.get_note(note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Заметка не найдена")
    return templates.TemplateResponse(request, "edit.html", {"note": note})


@app.post("/notes/{note_id}")
def update(note_id: int, title: str = Form(...), body: str = Form("")):
    if db.get_note(note_id) is None:
        raise HTTPException(status_code=404, detail="Заметка не найдена")
    title, body = clean(title, body)
    db.update_note(note_id, title, body)
    return RedirectResponse("/", status_code=303)


@app.post("/notes/{note_id}/delete")
def delete(note_id: int):
    db.delete_note(note_id)
    return RedirectResponse("/", status_code=303)
