import secrets
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app import auth, db
from app.auth import LoginRequired, current_user

BASE = Path(__file__).parent

load_dotenv()
SETTINGS = auth.settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="Заметки", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
app.add_middleware(
    SessionMiddleware,
    secret_key=SETTINGS.session_secret,
    max_age=auth.SESSION_MAX_AGE,
    same_site="lax",
)
templates = Jinja2Templates(directory=BASE / "templates")

User = sqlite3.Row


@app.exception_handler(LoginRequired)
def login_required(request: Request, exc: LoginRequired):
    return RedirectResponse("/login", status_code=303)


def login_failed(request: Request):
    return templates.TemplateResponse(
        request, "login.html", {"error": True}, status_code=400
    )


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {})


@app.get("/auth/login")
def auth_login(request: Request):
    state = secrets.token_urlsafe(32)
    request.session["oauth_state"] = state
    return RedirectResponse(auth.authorize_url(state), status_code=303)


@app.get("/auth/callback")
def auth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    # state одноразовый: забираем его из сессии при любом исходе
    expected = request.session.pop("oauth_state", None)
    if not (expected and state and secrets.compare_digest(expected, state)):
        raise HTTPException(status_code=400, detail="Неверный параметр state")
    if error or not code:
        return login_failed(request)
    try:
        profile = auth.fetch_user(auth.exchange_code(code))
    except auth.AuthError:
        return login_failed(request)
    user_id = db.upsert_user(profile["id"], profile["login"])
    request.session.clear()
    request.session["user_id"] = user_id
    return RedirectResponse("/", status_code=303)


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


def clean(title: str, body: str) -> tuple[str, str]:
    title = title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Заголовок не может быть пустым")
    return title, body.strip()


@app.get("/", response_class=HTMLResponse)
def index(request: Request, q: str = "", user: User = Depends(current_user)):
    q = q.strip()
    notes = db.search_notes(user["id"], q) if q else db.list_notes(user["id"])
    return templates.TemplateResponse(
        request, "index.html", {"notes": notes, "q": q, "user": user}
    )


@app.post("/notes")
def create(
    title: str = Form(...), body: str = Form(""), user: User = Depends(current_user)
):
    title, body = clean(title, body)
    db.create_note(title, body, owner_id=user["id"])
    return RedirectResponse("/", status_code=303)


@app.get("/notes/{note_id}", response_class=HTMLResponse)
def edit(request: Request, note_id: int, user: User = Depends(current_user)):
    note = db.get_note(note_id, user["id"])
    if note is None:
        raise HTTPException(status_code=404, detail="Заметка не найдена")
    return templates.TemplateResponse(request, "edit.html", {"note": note, "user": user})


@app.post("/notes/{note_id}")
def update(
    note_id: int,
    title: str = Form(...),
    body: str = Form(""),
    user: User = Depends(current_user),
):
    if db.get_note(note_id, user["id"]) is None:
        raise HTTPException(status_code=404, detail="Заметка не найдена")
    title, body = clean(title, body)
    db.update_note(note_id, user["id"], title, body)
    return RedirectResponse("/", status_code=303)


@app.post("/notes/{note_id}/delete")
def delete(note_id: int, user: User = Depends(current_user)):
    if not db.delete_note(note_id, user["id"]):
        raise HTTPException(status_code=404, detail="Заметка не найдена")
    return RedirectResponse("/", status_code=303)
