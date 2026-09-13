# -*- coding: utf-8 -*-
"""Authenticated pages and the persistent Origin board API."""

import html
import asyncio
import json
import os
import secrets
import sqlite3
import threading
import urllib.parse
import urllib.request
from urllib.error import HTTPError, URLError
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

router = APIRouter()

GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")
GITHUB_REDIRECT_URI = os.getenv(
    "GITHUB_REDIRECT_URI", "http://localhost:8000/auth/callback"
)
SESSION_COOKIE = "origin_session"
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]
DATABASE_PATH = os.getenv(
    "ORIGIN_DB_PATH",
    os.path.join(os.getenv("DATA_DIR", os.path.dirname(__file__)), "origin.db"),
)
_db_lock = threading.Lock()


def _db_connection():
    if DATABASE_URL:
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError(
                "Для PostgreSQL потрібен пакет psycopg[binary]."
            ) from exc
        return psycopg.connect(DATABASE_URL)
    connection = sqlite3.connect(DATABASE_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    return connection


def _init_database() -> None:
    if not DATABASE_URL:
        os.makedirs(os.path.dirname(os.path.abspath(DATABASE_PATH)), exist_ok=True)
    with _db_lock:
        connection = _db_connection()
        try:
            if DATABASE_URL:
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS origin_sessions "
                    "(session_id TEXT PRIMARY KEY, data JSONB NOT NULL)"
                )
            else:
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS origin_sessions "
                    "(session_id TEXT PRIMARY KEY, data TEXT NOT NULL)"
                )
            connection.commit()
        finally:
            connection.close()


def _load_session(session_id: str) -> Optional[Dict[str, Any]]:
    if not session_id:
        return None
    with _db_lock:
        connection = _db_connection()
        try:
            row = connection.execute(
                "SELECT data FROM origin_sessions WHERE session_id = %s"
                if DATABASE_URL
                else "SELECT data FROM origin_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if not row:
                return None
            data = row[0]
            return data if isinstance(data, dict) else json.loads(data)
        finally:
            connection.close()


def _find_github_session(user_data: Dict[str, Any]):
    github_id = str(user_data.get("id", ""))
    username = str(user_data.get("login", ""))
    if not github_id and not username:
        return None
    with _db_lock:
        connection = _db_connection()
        try:
            rows = connection.execute("SELECT session_id, data FROM origin_sessions").fetchall()
            for row in rows:
                data = row[1] if isinstance(row[1], dict) else json.loads(row[1])
                if (github_id and str(data.get("github_id", "")) == github_id) or (
                    not data.get("github_id") and username and data.get("username") == username
                ):
                    return row[0], data
            return None
        finally:
            connection.close()


def _save_session(session_id: str, session: Dict[str, Any]) -> None:
    serialized = json.dumps(session, ensure_ascii=False)
    with _db_lock:
        connection = _db_connection()
        try:
            if DATABASE_URL:
                from psycopg.types.json import Jsonb

                connection.execute(
                    "INSERT INTO origin_sessions (session_id, data) VALUES (%s, %s) "
                    "ON CONFLICT (session_id) DO UPDATE SET data = EXCLUDED.data",
                    (session_id, Jsonb(session)),
                )
            else:
                connection.execute(
                    "INSERT INTO origin_sessions (session_id, data) VALUES (?, ?) "
                    "ON CONFLICT(session_id) DO UPDATE SET data = excluded.data",
                    (session_id, serialized),
                )
            connection.commit()
        finally:
            connection.close()


def _delete_session(session_id: str) -> None:
    with _db_lock:
        connection = _db_connection()
        try:
            connection.execute(
                "DELETE FROM origin_sessions WHERE session_id = %s"
                if DATABASE_URL
                else "DELETE FROM origin_sessions WHERE session_id = ?",
                (session_id,),
            )
            connection.commit()
        finally:
            connection.close()


_init_database()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(9)}"


def _session_identity(session: Dict[str, Any]) -> str:
    return str(session.get("github_id") or session.get("username") or "")


def _friend_json(friend: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": friend.get("id", ""),
        "username": friend.get("username", "Користувач"),
        "avatar_url": friend.get("avatar_url", ""),
        "added_at": friend.get("added_at", ""),
    }


def _ensure_social_fields(session: Dict[str, Any]) -> None:
    session.setdefault("friends", [])
    session.setdefault("friend_invite_token", secrets.token_urlsafe(18))


def _find_session_by_invite(token: str):
    if not token or len(token) > 100:
        return None
    with _db_lock:
        connection = _db_connection()
        try:
            rows = connection.execute("SELECT session_id, data FROM origin_sessions").fetchall()
            for row in rows:
                data = row[1] if isinstance(row[1], dict) else json.loads(row[1])
                if data.get("active", True) is not False and data.get("friend_invite_token") == token:
                    return row[0], data
            return None
        finally:
            connection.close()


def _check_github_config() -> None:
    if not GITHUB_CLIENT_ID or not GITHUB_CLIENT_SECRET:
        raise HTTPException(
            status_code=503,
            detail="GitHub OAuth не налаштований: додайте GITHUB_CLIENT_ID і GITHUB_CLIENT_SECRET.",
        )


def _github_request(url: str, data: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    encoded = urllib.parse.urlencode(data).encode() if data is not None else None
    request = urllib.request.Request(url, data=encoded, headers=headers or {})
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def _session(request: Request) -> Dict[str, Any]:
    session_id = request.cookies.get(SESSION_COOKIE, "")
    session = _load_session(session_id)
    if not session or session.get("active", True) is False:
        raise HTTPException(status_code=401, detail="Сесія завершилася. Увійдіть знову.")
    request.state.origin_session_id = session_id
    request.state.origin_session = session
    session.setdefault("settings", {"language": "uk", "theme": "dark"})
    session.setdefault("boards", {})
    _ensure_social_fields(session)
    return session


def _optional_session(request: Request) -> Optional[Dict[str, Any]]:
    session_id = request.cookies.get(SESSION_COOKIE, "")
    session = _load_session(session_id)
    if session and session.get("active", True) is not False:
        request.state.origin_session_id = session_id
        request.state.origin_session = session
        session.setdefault("settings", {"language": "uk", "theme": "dark"})
        session.setdefault("boards", {})
        _ensure_social_fields(session)
    return session


def persist_request_session(request: Request) -> None:
    session_id = getattr(request.state, "origin_session_id", "")
    session = getattr(request.state, "origin_session", None)
    if session_id and session and not getattr(request.state, "origin_session_deleted", False):
        _save_session(session_id, session)


def _payload(request: Request, data: Any) -> Dict[str, Any]:
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="Некоректні дані.")
    return data


async def _json(request: Request) -> Dict[str, Any]:
    try:
        return _payload(request, await request.json())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Некоректний JSON.") from exc


def _text(value: Any, name: str, minimum: int = 1, maximum: int = 200) -> str:
    value = str(value or "").strip()
    if not minimum <= len(value) <= maximum:
        raise HTTPException(
            status_code=422,
            detail=f"{name} має містити від {minimum} до {maximum} символів.",
        )
    return value


def _board(session: Dict[str, Any], board_id: str) -> Dict[str, Any]:
    board = session["boards"].get(board_id)
    if not board:
        raise HTTPException(status_code=404, detail="Дошку не знайдено.")
    return board


def _category(board: Dict[str, Any], category_id: str) -> Dict[str, Any]:
    category = board["categories"].get(category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Категорію не знайдено.")
    return category


def _find_card(session: Dict[str, Any], card_id: str):
    for board in session["boards"].values():
        for category in board["categories"].values():
            if card_id in category["cards"]:
                return board, category, category["cards"][card_id]
    raise HTTPException(status_code=404, detail="Картку не знайдено.")


def _category_json(category: Dict[str, Any]) -> Dict[str, Any]:
    cards = sorted(category["cards"].values(), key=lambda item: item["position"])
    return {
        "id": category["id"],
        "name": category["name"],
        "color": category["color"],
        "width": category.get("width", 340),
        "position": category["position"],
        "cards": cards,
    }


def _board_json(board: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": board["id"],
        "title": board["title"],
        "description": board["description"],
        "created_at": board["created_at"],
        "categories": [
            _category_json(category)
            for category in sorted(
                board["categories"].values(), key=lambda item: item["position"]
            )
        ],
        "drawing": board.get("drawing", []),
    }


def _board_card(session: Dict[str, Any], board: Dict[str, Any]) -> str:
    avatar = html.escape(session.get("avatar_url", ""), quote=True)
    username = html.escape(session.get("username", "Гість"))
    avatar_markup = (
        f'<img class="avatar" src="{avatar}" alt="Аватар">'
        if avatar
        else '<span class="avatar avatar-fallback">✦</span>'
    )
    board_id = html.escape(board["id"], quote=True)
    return _app_page(
        session,
        f"""
        <div class="topbar">
          <a class="brand" href="/dashboard"><span class="mark">✦</span> origin</a>
          <div class="top-actions">
            <a class="back-link" href="/dashboard">← <span data-i18n="boards">Дошки</span></a>
            <div class="account">
              <button class="avatar-button" id="avatarButton" aria-label="Профіль">{avatar_markup}</button>
              <div class="menu" id="accountMenu">
                <a href="/settings" data-i18n="settings">Налаштування</a>
                <a href="/auth/logout" data-i18n="logout">Вийти</a>
              </div>
            </div>
          </div>
        </div>
        <main class="board-page" data-board-id="{board_id}">
          <section class="board-heading">
            <div>
              <a class="muted-link" href="/dashboard">Origin</a>
              <h1 id="boardTitle"></h1>
              <p id="boardDescription" class="muted"></p>
            </div>
            <div class="heading-actions">
              <button class="button ghost" id="editBoard" data-i18n="editBoard">Редагувати</button>
              <button class="button primary" id="addColumn" data-i18n="addColumn">＋ Колонка</button>
            </div>
          </section>
          <section class="board-wrap" id="boardWrap">
            <div class="board-content" id="boardContent">
              <canvas id="drawingCanvas" aria-label="Малювання на дошці"></canvas>
              <div id="columns" class="columns"></div>
            </div>
            <button id="drawToggle" class="draw-toggle" title="Малювати">✎</button>
            <div id="emptyBoard" class="empty hidden">
              <strong data-i18n="emptyBoard">Створи першу колонку, щоб почати.</strong>
            </div>
          </section>
        </main>
        <div class="modal" id="modal"><form class="dialog" id="dialogForm">
          <button class="close" id="closeModal" type="button">×</button>
          <h2 id="dialogTitle"></h2><div id="dialogBody"></div>
          <div class="dialog-actions"><button type="button" class="button ghost" id="cancelDialog" data-i18n="cancel">Скасувати</button><button class="button primary" type="submit" data-i18n="save">Зберегти</button></div>
          <p class="form-status" id="formStatus"></p>
        </form></div>
        <script>
          window.ORIGIN_BOARD_ID = "{board_id}";
          window.ORIGIN_USERNAME = {username!r};
        </script>
        <script>{_BOARD_SCRIPT}</script>
        """,
    )


def _app_page(session: Dict[str, Any], content: str) -> str:
    username = html.escape(session.get("username", "Гість"))
    avatar = html.escape(session.get("avatar_url", ""), quote=True)
    avatar_markup = (
        f'<img class="avatar" src="{avatar}" alt="Аватар">'
        if avatar
        else '<span class="avatar avatar-fallback">✦</span>'
    )
    return f"""<!doctype html>
<html lang="uk"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Origin — робочий простір</title><style>{_APP_CSS}</style></head><body>
<div class="app"><div class="page">{content}</div></div>
<script>{_COMMON_SCRIPT}</script></body></html>"""


_APP_CSS = r"""
:root{--bg:#f7f8fc;--surface:#fff;--surface-2:#eef0f6;--ink:#17212b;--muted:#697386;--line:#e3e6ef;--blue:#5865f2;--blue-2:#eef0ff;--shadow:0 18px 45px #26345d12}
body.dark{--bg:#0f131d;--surface:#171c28;--surface-2:#202735;--ink:#f4f6fb;--muted:#9da6ba;--line:#ffffff18;--blue:#7d86ff;--blue-2:#262b57;--shadow:0 18px 45px #0005}
*{box-sizing:border-box}body{margin:0;color:var(--ink);background:var(--bg);font:15px Inter,ui-sans-serif,system-ui,-apple-system,sans-serif;transition:background .2s,color .2s}a{color:inherit;text-decoration:none}.app{min-height:100vh}.page{width:min(1400px,calc(100% - 32px));margin:auto;padding:25px 0 60px}.topbar{height:50px;display:flex;align-items:center;justify-content:space-between}.brand{display:flex;align-items:center;gap:9px;font-size:22px;font-weight:850;letter-spacing:-.7px}.mark{width:31px;height:31px;display:grid;place-items:center;border-radius:10px;color:#fff;background:var(--blue);transform:rotate(-6deg)}.top-actions,.account{display:flex;align-items:center;gap:14px}.back-link,.muted-link{color:var(--muted);font-weight:700}.avatar-button{width:42px;height:42px;padding:0;border:0;border-radius:50%;background:transparent;cursor:pointer}.avatar{width:42px;height:42px;display:grid;place-items:center;border:2px solid var(--blue);border-radius:50%;object-fit:cover}.avatar-fallback{color:#fff;background:linear-gradient(135deg,var(--blue),#39c78a)}.account{position:relative}.menu{position:absolute;right:0;top:52px;z-index:10;display:none;min-width:165px;padding:8px;border:1px solid var(--line);border-radius:14px;background:var(--surface);box-shadow:var(--shadow)}.menu.open{display:block}.menu a{display:block;padding:10px;border-radius:8px;color:var(--ink)}.menu a:hover{background:var(--surface-2)}.board-heading{display:flex;justify-content:space-between;align-items:end;gap:20px;padding:58px 0 27px}.board-heading h1{margin:7px 0 5px;font-size:clamp(32px,5vw,52px);letter-spacing:-2px}.muted{margin:0;color:var(--muted)}.heading-actions,.dialog-actions{display:flex;gap:9px}.button{border:0;border-radius:11px;padding:11px 15px;font:inherit;font-weight:750;cursor:pointer;transition:.18s}.button:hover{transform:translateY(-1px)}.primary{color:#fff;background:var(--blue);box-shadow:0 8px 20px #5865f233}.ghost{color:var(--ink);background:var(--surface);border:1px solid var(--line)}.board-wrap{position:relative;min-height:760px;padding:24px;border:1px solid var(--line);border-radius:22px;overflow:hidden;cursor:default;background-color:var(--surface-2);background-image:radial-gradient(var(--muted) 1px,transparent 1px);background-size:18px 18px;box-shadow:var(--shadow)}.board-content{position:absolute;inset:0;transform:translate(0,0);transform-origin:0 0;will-change:transform}.columns{position:relative;z-index:1;display:flex;align-items:flex-start;gap:18px;min-height:720px;overflow:visible;padding:24px}.column{position:relative;flex:0 0 340px;min-height:220px;padding:14px;border:1px solid var(--line);border-radius:16px;background:color-mix(in srgb,var(--surface) 92%,transparent);box-shadow:0 8px 22px #18233d10}.column-head{display:flex;justify-content:space-between;gap:8px;align-items:center;margin-bottom:11px}.column-title{font-weight:850}.count{color:var(--muted);font-size:12px}.column-tools{display:flex;gap:3px}.icon-btn{padding:5px;border:0;border-radius:7px;color:var(--muted);background:transparent;cursor:pointer}.icon-btn:hover{background:var(--surface-2);color:var(--ink)}.resize-handle{position:absolute;top:10px;right:-5px;bottom:10px;width:10px;cursor:ew-resize;border-radius:8px}.resize-handle:hover{background:var(--blue)}.task{display:block;width:100%;margin:8px 0;padding:15px;border:1px solid var(--line);border-radius:12px;color:var(--ink);background:var(--surface);text-align:left;box-shadow:0 3px 10px #18233d0b;cursor:pointer}.task:hover{border-color:var(--blue)}.task-title{display:block;margin-bottom:9px;font-weight:750}.task-meta{display:flex;gap:10px;color:var(--muted);font-size:12px}.add-card{width:100%;padding:11px;border:0;border-radius:9px;color:var(--muted);background:transparent;text-align:left;cursor:pointer}.add-card:hover{background:var(--surface-2);color:var(--ink)}.empty{position:absolute;inset:0;display:grid;place-items:center;color:var(--muted);pointer-events:none}.hidden{display:none!important}.draw-toggle{position:absolute;right:18px;bottom:18px;z-index:3;width:42px;height:42px;border:1px solid var(--line);border-radius:50%;color:var(--ink);background:var(--surface);font-size:20px;cursor:pointer;box-shadow:var(--shadow)}.draw-toggle.active{color:#fff;background:var(--blue)}#drawingCanvas{position:absolute;inset:0;width:100%;height:100%;z-index:2;pointer-events:none}.modal{position:fixed;inset:0;z-index:20;display:none;place-items:center;padding:20px;background:#070a12aa}.modal.open{display:grid}.dialog{width:min(100%,520px);max-height:90vh;overflow:auto;padding:25px;border:1px solid var(--line);border-radius:20px;background:var(--surface);box-shadow:0 25px 80px #0007}.dialog h2{margin:0 0 20px}.close{float:right;border:0;color:var(--muted);background:transparent;font-size:25px;cursor:pointer}.field{margin-bottom:15px}.field label{display:block;margin-bottom:7px;color:var(--muted);font-size:13px;font-weight:750}.field input,.field textarea,.field select{width:100%;padding:11px 12px;border:1px solid var(--line);border-radius:10px;outline:0;color:var(--ink);background:var(--surface-2);font:inherit}.field textarea{min-height:115px;resize:vertical}.dialog-actions{justify-content:flex-end;margin-top:20px}.form-status{min-height:18px;margin:12px 0 0;color:#e36b68;font-size:13px}.checklist{margin:12px 0;padding:0;list-style:none}.checklist li{display:flex;align-items:center;gap:8px;padding:7px 0}.checklist input{accent-color:var(--blue)}.checklist span{flex:1}.checklist .done{text-decoration:line-through;color:var(--muted)}.check-add{display:flex;gap:7px}.check-add input{flex:1}
@media(max-width:700px){.page{width:min(100% - 22px,1180px)}.board-heading{display:block;padding-top:36px}.heading-actions{margin-top:18px}.board-wrap{padding:12px}.column{flex-basis:82vw}.back-link{display:none}}
"""


_COMMON_SCRIPT = r"""
(() => {
  const theme = localStorage.getItem('origin-theme') || 'dark';
  document.body.classList.toggle('dark', theme === 'dark');
  window.originLanguage = localStorage.getItem('origin-language') || 'uk';
  const translations = {
    uk:{boards:'Дошки',friends:'Друзі',friendsIntro:'Додавай друзів за спеціальним посиланням.',createLink:'Створити посилання',addFriend:'Додати друга',emptyFriends:'Тут ще немає друзів.',linkCopied:'Посилання скопійовано.',friendAdded:'Друг доданий.',settings:'Налаштування',logout:'Вийти',editBoard:'Редагувати',addColumn:'＋ Колонка',cancel:'Скасувати',save:'Зберегти',language:'Мова',theme:'Тема',light:'Світла',dark:'Темна',profile:'Профіль',newBoard:'Нова дошка',create:'Створити',title:'Назва',description:'Опис',columnName:'Назва колонки',cardTitle:'Назва картки',details:'Детальний опис',emptyBoard:'Створи першу колонку, щоб почати.',emptyBoards:'Створи першу дошку — це займе секунду.',addCard:'＋ Додати картку',delete:'Видалити',rename:'Перейменувати',checklist:'Чекліст',addItem:'Додати пункт',drawing:'Малювання збережено.',workspace:'Твій робочий простір',hello:'Вітаємо',dashboardIntro:'Збирай ідеї, рухай картки та доводь задумане до результату.',preferences:'Персоналізація',nickname:'Нікнейм',avatarLabel:'Аватарка',columns:'колонки'},
    en:{boards:'Boards',friends:'Friends',friendsIntro:'Add friends using a special link.',createLink:'Create link',addFriend:'Add friend',emptyFriends:'You have no friends yet.',linkCopied:'Link copied.',friendAdded:'Friend added.',settings:'Settings',logout:'Log out',editBoard:'Edit',addColumn:'＋ Column',cancel:'Cancel',save:'Save',language:'Language',theme:'Theme',light:'Light',dark:'Dark',profile:'Profile',newBoard:'New board',create:'Create',title:'Title',description:'Description',columnName:'Column name',cardTitle:'Card title',details:'Detailed description',emptyBoard:'Create your first column to get started.',emptyBoards:'Create your first board — it only takes a second.',addCard:'＋ Add card',delete:'Delete',rename:'Rename',checklist:'Checklist',addItem:'Add item',drawing:'Drawing saved.',workspace:'Your workspace',hello:'Welcome',dashboardIntro:'Gather ideas, move cards, and turn plans into progress.',preferences:'Personalization',nickname:'Nickname',avatarLabel:'Avatar',columns:'columns'}
  };
  window.t = key => (translations[window.originLanguage] || translations.uk)[key] || key;
  window.applyLanguage = () => { document.documentElement.lang=window.originLanguage; document.querySelectorAll('[data-i18n]').forEach(el=>el.textContent=t(el.dataset.i18n)); };
  window.setTheme = value => { document.body.classList.toggle('dark',value==='dark'); localStorage.setItem('origin-theme',value); };
  window.toggleTheme = () => setTheme(document.body.classList.contains('dark')?'light':'dark');
  const avatarButton=document.getElementById('avatarButton'), menu=document.getElementById('accountMenu');
  if(avatarButton && menu) avatarButton.addEventListener('click',()=>menu.classList.toggle('open'));
  applyLanguage();
})();
"""


_BOARD_SCRIPT = r"""
(() => {
  const boardId = window.ORIGIN_BOARD_ID;
  const boardWrap = document.getElementById('boardWrap'), boardContent = document.getElementById('boardContent');
  const columnsEl = document.getElementById('columns'), emptyEl = document.getElementById('emptyBoard');
  const modal = document.getElementById('modal'), form = document.getElementById('dialogForm'), body = document.getElementById('dialogBody');
  const titleEl = document.getElementById('dialogTitle'), statusEl = document.getElementById('formStatus');
  let board = null, action = null, drawing = [], drawingMode = false, camera = {x:0,y:0}, panning = false, panStart = null, spaceDown = false;
  const esc = value => String(value ?? '');
  const api = async (url, options={}) => { const response=await fetch(url,{headers:{'Content-Type':'application/json',...(options.headers||{})},...options}); const data=await response.json().catch(()=>({})); if(!response.ok) throw new Error(data.detail||'Request failed'); return data; };
  const input = (label,key,value='',area=false) => { const wrap=document.createElement('div'); wrap.className='field'; const l=document.createElement('label'); l.textContent=label; const el=document.createElement(area?'textarea':'input'); el.name=key; el.value=value; el.required=key==='name'||key==='title'; wrap.append(l,el); return wrap; };
  const open = (title, fields, callback) => { titleEl.textContent=title; body.replaceChildren(...fields); action=callback; statusEl.textContent=''; modal.classList.add('open'); };
  const close = () => modal.classList.remove('open');
  document.getElementById('closeModal').onclick=close; document.getElementById('cancelDialog').onclick=close;
  modal.addEventListener('click',e=>{if(e.target===modal)close()});
  form.addEventListener('submit',async e=>{e.preventDefault(); statusEl.textContent=''; if(!action)return; try { await action(new FormData(form)); close(); await load(); } catch(error){statusEl.textContent=error.message;}});
  const makeTask = card => { const el=document.createElement('button'); el.className='task'; const title=document.createElement('span'); title.className='task-title'; title.textContent=esc(card.title); const meta=document.createElement('span'); meta.className='task-meta'; meta.textContent=`${card.checklist.filter(x=>x.done).length}/${card.checklist.length} ✓`; el.append(title,meta); el.onclick=()=>cardDialog(card); return el; };
  function render() {
    document.getElementById('boardTitle').textContent=esc(board.title); document.getElementById('boardDescription').textContent=esc(board.description);
    columnsEl.replaceChildren(); emptyEl.classList.toggle('hidden',board.categories.length>0);
    board.categories.forEach(category=>{ const col=document.createElement('section'); col.className='column'; col.style.flexBasis=`${category.width||340}px`; const head=document.createElement('div'); head.className='column-head'; const name=document.createElement('span'); name.className='column-title'; name.textContent=esc(category.name); const count=document.createElement('span'); count.className='count'; count.textContent=category.cards.length; const tools=document.createElement('span'); tools.className='column-tools'; const rename=document.createElement('button'); rename.className='icon-btn'; rename.textContent='✎'; rename.title=t('rename'); rename.onclick=()=>categoryDialog(category); const remove=document.createElement('button'); remove.className='icon-btn'; remove.textContent='×'; remove.title=t('delete'); remove.onclick=()=>deleteCategory(category); tools.append(rename,remove); head.append(name,count,tools); col.append(head); const resizeHandle=document.createElement('div'); resizeHandle.className='resize-handle'; resizeHandle.title='Змінити розмір'; resizeHandle.onpointerdown=e=>startResize(e,col,category); col.append(resizeHandle); category.cards.forEach(card=>col.append(makeTask(card))); const add=document.createElement('button'); add.type='button'; add.className='add-card'; add.textContent=t('addCard'); add.onclick=e=>{e.preventDefault();e.stopPropagation();cardDialog(null,category)}; col.append(add); columnsEl.append(col); });
    draw();
  }
  async function load(){board=await api(`/api/boards/${encodeURIComponent(boardId)}`); drawing=board.drawing||[]; render();}
  function startResize(event,column,category){event.preventDefault();event.stopPropagation();const startX=event.clientX,startWidth=column.getBoundingClientRect().width;const move=e=>{column.style.flexBasis=`${Math.max(260,Math.min(600,startWidth+e.clientX-startX))}px`};const stop=async()=>{document.removeEventListener('pointermove',move);document.removeEventListener('pointerup',stop);const width=Math.round(column.getBoundingClientRect().width);category.width=width;try{await api(`/api/boards/${boardId}/categories/${category.id}`,{method:'PATCH',body:JSON.stringify({width})})}catch(error){statusEl.textContent=error.message}};document.addEventListener('pointermove',move);document.addEventListener('pointerup',stop);}
  function categoryDialog(category){open(category?t('rename'):t('addColumn'),[input(t('columnName'),'name',category?.name||'')],async data=>{const options={method:category?'PATCH':'POST',body:JSON.stringify({name:data.get('name')})}; await api(category?`/api/boards/${boardId}/categories/${category.id}`:`/api/boards/${boardId}/categories`,options);});}
  function cardDialog(card,category){ if(card){const fields=[input(t('cardTitle'),'title',card.title),input(t('details'),'description',card.description||'',true)]; const list=document.createElement('div'); list.className='field'; const label=document.createElement('label'); label.textContent=t('checklist'); list.append(label); const ul=document.createElement('ul'); ul.className='checklist'; (card.checklist||[]).forEach(item=>{const li=document.createElement('li'); const box=document.createElement('input'); box.type='checkbox'; box.checked=item.done; box.onchange=()=>api(`/api/cards/${card.id}/checklist/${item.id}`,{method:'PATCH',body:JSON.stringify({done:box.checked})}); const text=document.createElement('span'); text.textContent=item.text; if(item.done)text.className='done'; li.append(box,text); ul.append(li)}); const add=document.createElement('div'); add.className='check-add'; const addInput=document.createElement('input'); addInput.placeholder=t('addItem'); const addBtn=document.createElement('button'); addBtn.type='button'; addBtn.className='button ghost'; addBtn.textContent='＋'; addBtn.onclick=async()=>{if(addInput.value.trim()){await api(`/api/cards/${card.id}/checklist`,{method:'POST',body:JSON.stringify({text:addInput.value})}); close(); await load(); cardDialog(board.categories.flatMap(x=>x.cards).find(x=>x.id===card.id),category)}}; add.append(addInput,addBtn); list.append(ul,add); fields.push(list); open(t('details'),fields,async data=>api(`/api/cards/${card.id}`,{method:'PATCH',body:JSON.stringify({title:data.get('title'),description:data.get('description')})})); } else open(t('addCard'),[input(t('cardTitle'),'title',''),input(t('details'),'description','',true)],async data=>api(`/api/boards/${boardId}/categories/${category.id}/cards`,{method:'POST',body:JSON.stringify({title:data.get('title'),description:data.get('description')})})); }
  async function deleteCategory(category){if(confirm(`${t('delete')} "${category.name}"?`))await api(`/api/boards/${boardId}/categories/${category.id}`,{method:'DELETE'}).then(load);}
  document.getElementById('addColumn').onclick=()=>categoryDialog(null);
  document.getElementById('editBoard').onclick=()=>open(t('editBoard'),[input(t('title'),'title',board.title),input(t('description'),'description',board.description,true)],async data=>api(`/api/boards/${boardId}`,{method:'PATCH',body:JSON.stringify({title:data.get('title'),description:data.get('description')})}));
  const canvas=document.getElementById('drawingCanvas'), ctx=canvas.getContext('2d'), toggle=document.getElementById('drawToggle');
  function resize(){const rect=canvas.parentElement.getBoundingClientRect(),ratio=window.devicePixelRatio||1; canvas.width=rect.width*ratio; canvas.height=rect.height*ratio; canvas.style.width=rect.width+'px';canvas.style.height=rect.height+'px';ctx.setTransform(1,0,0,1,0,0);ctx.scale(ratio,ratio);draw();} window.addEventListener('resize',resize);
  function draw(){if(!canvas.width)return; const rect=canvas.getBoundingClientRect();ctx.clearRect(0,0,rect.width,rect.height);ctx.strokeStyle=getComputedStyle(document.body).getPropertyValue('--blue');ctx.lineWidth=3;ctx.lineCap='round';drawing.forEach(stroke=>{ctx.beginPath();stroke.forEach((p,i)=>i?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1]));ctx.stroke()});}
  function backgroundPoint(clientX,clientY){canvas.style.pointerEvents='none';const target=document.elementFromPoint(clientX,clientY);canvas.style.pointerEvents=drawingMode?'auto':'none';return !target?.closest('.column,.task');}
  async function saveDrawing(){return api(`/api/boards/${boardId}/drawing`,{method:'PUT',body:JSON.stringify({drawing})});}
  let stroke=null; canvas.addEventListener('pointerdown',e=>{if(!drawingMode||spaceDown||!backgroundPoint(e.clientX,e.clientY))return;stroke=[];drawing.push(stroke);const r=canvas.getBoundingClientRect();stroke.push([e.clientX-r.left,e.clientY-r.top]);canvas.setPointerCapture(e.pointerId)});canvas.addEventListener('pointermove',e=>{if(!stroke)return;const r=canvas.getBoundingClientRect();stroke.push([e.clientX-r.left,e.clientY-r.top]);draw()});canvas.addEventListener('pointerup',async()=>{if(stroke){stroke=null;await saveDrawing()}});
  async function undoDrawing(){if(stroke||!drawing.length)return;drawing.pop();draw();try{await saveDrawing()}catch(error){statusEl.textContent=error.message;}}
  function setCamera(){boardContent.style.transform=`translate(${camera.x}px,${camera.y}px)`;}
  boardWrap.addEventListener('pointerdown',e=>{if(e.button!==1&&!spaceDown)return;e.preventDefault();panning=true;panStart={x:e.clientX-camera.x,y:e.clientY-camera.y};boardWrap.setPointerCapture(e.pointerId);boardWrap.style.cursor='grabbing';});
  boardWrap.addEventListener('pointermove',e=>{if(!panning)return;camera.x=e.clientX-panStart.x;camera.y=e.clientY-panStart.y;setCamera();});
  boardWrap.addEventListener('pointerup',e=>{if(!panning)return;panning=false;boardWrap.releasePointerCapture(e.pointerId);boardWrap.style.cursor=spaceDown?'grab':'default';});
  window.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='z'&&!e.shiftKey){const target=e.target;if(!['INPUT','TEXTAREA'].includes(target.tagName)&&!target.isContentEditable){e.preventDefault();undoDrawing();}return;}if(e.code==='Space'&&!e.repeat){spaceDown=true;boardWrap.style.cursor='grab';}});
  window.addEventListener('keyup',e=>{if(e.code==='Space'){spaceDown=false;boardWrap.style.cursor='default';}});
  toggle.onclick=()=>{drawingMode=!drawingMode;toggle.classList.toggle('active',drawingMode);canvas.style.pointerEvents=drawingMode?'auto':'none';};
  load().then(resize).catch(error=>{statusEl.textContent=error.message});
})();
"""


@router.get("/auth/github")
async def github_login():
    _check_github_config()
    params = urlencode({"client_id": GITHUB_CLIENT_ID, "redirect_uri": GITHUB_REDIRECT_URI, "scope": "read:user"})
    return RedirectResponse(f"https://github.com/login/oauth/authorize?{params}")


@router.get("/auth/callback")
async def github_callback(code: Optional[str] = None, error: Optional[str] = None):
    _check_github_config()
    if error:
        return HTMLResponse(f"<h3>Авторизацію скасовано: {html.escape(error)}</h3>", status_code=400)
    if not code:
        return HTMLResponse("<h3>GitHub не повернув код авторизації.</h3>", status_code=400)
    try:
        token_data = await asyncio.to_thread(
            _github_request,
            "https://github.com/login/oauth/access_token",
            {"client_id": GITHUB_CLIENT_ID, "client_secret": GITHUB_CLIENT_SECRET, "code": code, "redirect_uri": GITHUB_REDIRECT_URI},
            {"Accept": "application/json"},
        )
        access_token = token_data.get("access_token")
        if not access_token:
            return HTMLResponse(
                "<h3>Помилка авторизації через GitHub: "
                f"{html.escape(token_data.get('error_description', 'невідома помилка'))}</h3>",
                status_code=400,
            )
        user_data = await asyncio.to_thread(
            _github_request,
            "https://api.github.com/user",
            None,
            {"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"},
        )
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        return HTMLResponse(
            f"<h3>Не вдалося зв'язатися з GitHub: {html.escape(str(exc))}</h3>",
            status_code=502,
        )
    existing = _find_github_session(user_data)
    if existing:
        session_id, session = existing
        session["username"] = user_data.get("login", session.get("username", "Гість"))
        session["avatar_url"] = user_data.get("avatar_url", session.get("avatar_url", ""))
        session["active"] = True
    else:
        session_id = secrets.token_urlsafe(32)
        session = {
            "github_id": str(user_data.get("id", "")),
            "username": user_data.get("login", "Гість"),
            "avatar_url": user_data.get("avatar_url", ""),
            "settings": {"language": "uk", "theme": "dark"},
            "boards": {},
            "active": True,
        }
    _save_session(session_id, session)
    response = RedirectResponse("/boards", status_code=303)
    response.set_cookie(SESSION_COOKIE, session_id, httponly=True, samesite="lax", max_age=60 * 60 * 24 * 7)
    return response


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    session = _optional_session(request)
    if not session:
        return RedirectResponse("/login", status_code=303)
    username = html.escape(session.get("username", "Гість"))
    avatar = html.escape(session.get("avatar_url", ""), quote=True)
    avatar_markup = f'<img class="avatar" src="{avatar}" alt="Аватар">' if avatar else '<span class="avatar avatar-fallback">✦</span>'
    content = f"""
    <div class="topbar"><a class="brand" href="/dashboard"><span class="mark">✦</span> origin</a>
      <div class="account"><button class="avatar-button" id="avatarButton" aria-label="Профіль">{avatar_markup}</button>
      <div class="menu" id="accountMenu"><a href="/settings" data-i18n="settings">Налаштування</a><a href="/auth/logout" data-i18n="logout">Вийти</a></div></div>
    </div>
    <main class="dashboard"><section class="welcome"><p class="eyebrow" data-i18n="workspace">Твій робочий простір</p><h1><span data-i18n="hello">Вітаємо</span>, {username}! 👋</h1><p class="muted" data-i18n="dashboardIntro">Збирай ідеї, рухай картки та доводь задумане до результату.</p></section>
      <nav class="dashboard-tabs" aria-label="Розділи"><button class="dashboard-tab active" data-tab="boards" data-i18n="boards">Дошки</button><button class="dashboard-tab" data-tab="friends" data-i18n="friends">Друзі</button></nav>
      <section class="dashboard-panel active" data-panel="boards"><div class="list-head"><h2 data-i18n="boards">Дошки</h2><button class="button primary" id="quickCreate" data-i18n="newBoard">＋ Нова дошка</button></div><div id="boardList" class="board-grid"></div></section>
      <section class="dashboard-panel" data-panel="friends"><div class="list-head"><div><h2 data-i18n="friends">Друзі</h2><p class="muted" data-i18n="friendsIntro">Додавай друзів за спеціальним посиланням.</p></div><button class="button primary" id="createInvite" data-i18n="createLink">Створити посилання</button></div><div class="friend-add"><input id="friendLink" placeholder="Встав посилання друга"><button class="button ghost" id="addFriend" data-i18n="addFriend">Додати друга</button></div><p class="form-status" id="friendsStatus"></p><div id="friendList" class="friend-grid"></div></section></main>
    <script>
    (()=>{{const list=document.getElementById('boardList'),friendList=document.getElementById('friendList'),status=document.getElementById('friendsStatus');const api=async(url,options={{}})=>{{const r=await fetch(url,{{headers:{{'Content-Type':'application/json'}},...options}});const x=await r.json().catch(()=>({{}}));if(!r.ok)throw new Error(x.detail||'Помилка');return x}};const renderBoards=async()=>{{const r=await api('/api/boards');list.replaceChildren();if(!r.length){{const e=document.createElement('p');e.className='muted';e.textContent=window.t('emptyBoards');list.append(e);return}}r.forEach(b=>{{const a=document.createElement('a');a.className='board-tile';a.href='/boards/'+encodeURIComponent(b.id);const h=document.createElement('h3');h.textContent=b.title;const p=document.createElement('p');p.textContent=b.description||' ';const s=document.createElement('span');s.textContent=b.categories+' '+window.t('columns');a.append(h,p,s);list.append(a)}})}};const renderFriends=async()=>{{const r=await api('/api/friends');friendList.replaceChildren();if(!r.friends.length){{const e=document.createElement('p');e.className='muted';e.textContent=window.t('emptyFriends');friendList.append(e);return}}r.friends.forEach(f=>{{const card=document.createElement('div');card.className='friend-card';const avatar=f.avatar_url?`<img src="${{f.avatar_url}}" alt="">`:'<span>✦</span>';card.innerHTML=avatar+`<strong>${{f.username}}</strong>`;friendList.append(card)}})}};document.querySelectorAll('.dashboard-tab').forEach(tab=>tab.onclick=()=>{{document.querySelectorAll('.dashboard-tab,.dashboard-panel').forEach(el=>el.classList.remove('active'));tab.classList.add('active');document.querySelector(`[data-panel="${{tab.dataset.tab}}"]`).classList.add('active');if(tab.dataset.tab==='friends')renderFriends()}});document.getElementById('quickCreate').onclick=()=>location.href='/boards/new';document.getElementById('createInvite').onclick=async()=>{{try{{const x=await api('/api/friends/invite',{{method:'POST'}});await navigator.clipboard.writeText(x.link);status.textContent=window.t('linkCopied')}}catch(e){{status.textContent=e.message}}}};document.getElementById('addFriend').onclick=async()=>{{try{{await api('/api/friends/add',{{method:'POST',body:JSON.stringify({{link:document.getElementById('friendLink').value}})}});status.textContent=window.t('friendAdded');document.getElementById('friendLink').value='';renderFriends()}}catch(e){{status.textContent=e.message}}}};renderBoards()}})();
    </script>
    """
    return HTMLResponse(_app_page(session, content).replace("</style>", ".welcome{padding:58px 0 35px}.eyebrow{display:inline-block;margin:0 0 14px;color:var(--blue);font-weight:800;text-transform:uppercase;font-size:12px;letter-spacing:.8px}.welcome h1{margin:0 0 12px;font-size:clamp(34px,6vw,60px);letter-spacing:-2px}.welcome .muted{max-width:560px;margin-bottom:25px}.dashboard-tabs{display:flex;gap:8px;margin-bottom:22px;border-bottom:1px solid var(--line)}.dashboard-tab{padding:11px 17px;border:0;border-bottom:2px solid transparent;color:var(--muted);background:transparent;font:inherit;font-weight:750;cursor:pointer}.dashboard-tab.active{color:var(--blue);border-bottom-color:var(--blue)}.dashboard-panel{display:none}.dashboard-panel.active{display:block}.list-head{display:flex;align-items:center;justify-content:space-between;gap:15px;margin-bottom:15px}.list-head h2{margin:0;font-size:25px}.list-head .muted{margin:5px 0 0}.board-grid,.friend-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:15px}.board-tile{min-height:150px;padding:20px;border:1px solid var(--line);border-radius:17px;background:var(--surface);box-shadow:var(--shadow);transition:.2s}.board-tile:hover{transform:translateY(-3px);border-color:var(--blue)}.board-tile h3{margin:0 0 8px;font-size:19px}.board-tile p{min-height:42px;margin:0 0 14px;color:var(--muted);line-height:1.45}.board-tile span{color:var(--blue);font-size:12px;font-weight:750}.friend-add{display:flex;gap:9px;margin:22px 0 10px}.friend-add input{flex:1;min-width:0;padding:11px 12px;border:1px solid var(--line);border-radius:10px;color:var(--ink);background:var(--surface);font:inherit}.friend-card{display:flex;align-items:center;gap:12px;padding:16px;border:1px solid var(--line);border-radius:15px;background:var(--surface)}.friend-card img,.friend-card>span{width:38px;height:38px;display:grid;place-items:center;border:2px solid var(--blue);border-radius:50%;object-fit:cover}.friend-card strong{font-size:16px}</style>"))


@router.get("/boards", response_class=HTMLResponse)
async def boards_page(request: Request):
    return await dashboard(request)


@router.get("/boards/new", response_class=HTMLResponse)
async def new_board(request: Request):
    session = _optional_session(request)
    if not session:
        return RedirectResponse("/login", status_code=303)
    content = """
    <div class="topbar"><a class="brand" href="/dashboard"><span class="mark">✦</span> origin</a><a class="back-link" href="/dashboard">← <span data-i18n="boards">Дошки</span></a></div>
    <main class="new-board-page"><form id="newBoardForm" class="dialog"><h1 data-i18n="newBoard">Нова дошка</h1><div class="field"><label data-i18n="title">Назва</label><input name="title" maxlength="80" required autofocus></div><div class="field"><label data-i18n="description">Опис</label><textarea name="description" maxlength="300"></textarea></div><div class="dialog-actions"><a class="button ghost" href="/dashboard" data-i18n="cancel">Скасувати</a><button class="button primary" data-i18n="create">Створити</button></div><p id="status" class="form-status"></p></form></main>
    <script>(()=>{const form=document.getElementById('newBoardForm');form.onsubmit=async e=>{e.preventDefault();const data=Object.fromEntries(new FormData(form));const r=await fetch('/api/boards',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});const x=await r.json();if(r.ok)location.href='/boards/'+encodeURIComponent(x.id);else document.getElementById('status').textContent=x.detail||'Помилка';}})();</script>
    """
    return HTMLResponse(_app_page(session, content).replace("</style>", ".new-board-page{display:grid;place-items:center;min-height:70vh}.new-board-page .dialog{width:min(100%,510px)}.new-board-page h1{margin:0 0 25px}</style>"))


@router.get("/boards/{board_id}", response_class=HTMLResponse)
async def board_page(request: Request, board_id: str):
    session = _optional_session(request)
    if not session:
        return RedirectResponse("/login", status_code=303)
    board = _board(session, board_id)
    return HTMLResponse(_board_card(session, board))


@router.post("/profile")
async def update_profile(request: Request):
    session = _session(request)
    payload = await _json(request)
    nickname = _text(payload.get("nickname"), "Нікнейм", 2, 30)
    avatar = payload.get("avatar")
    if avatar is not None:
        allowed = ("data:image/png;base64,", "data:image/jpeg;base64,", "data:image/webp;base64,", "data:image/gif;base64,")
        if not isinstance(avatar, str) or not avatar.startswith(allowed):
            raise HTTPException(status_code=422, detail="Оберіть коректний файл зображення.")
        if len(avatar) > 7_000_000:
            raise HTTPException(status_code=422, detail="Аватарка завелика. Максимум — 5 МБ.")
        session["avatar_url"] = avatar
    session["username"] = nickname
    return {"message": "Профіль оновлено.", "username": nickname}


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    session = _optional_session(request)
    if not session:
        return RedirectResponse("/login", status_code=303)
    username = html.escape(session.get("username", "Гість"), quote=True)
    avatar = html.escape(session.get("avatar_url", ""), quote=True)
    content = f"""
    <div class="topbar"><a class="brand" href="/dashboard"><span class="mark">✦</span> origin</a><a class="back-link" href="/dashboard">← <span data-i18n="boards">Дошки</span></a></div>
    <main class="settings-page"><div class="settings-card"><p class="eyebrow" data-i18n="settings">Налаштування</p><h1 data-i18n="preferences">Персоналізація</h1>
    <form id="settingsForm"><div class="field"><label data-i18n="language">Мова</label><select name="language"><option value="uk">Українська</option><option value="en">English</option></select></div><div class="field"><label data-i18n="theme">Тема</label><select name="theme"><option value="light" data-i18n="light">Світла</option><option value="dark" data-i18n="dark">Темна</option></select></div><button class="button primary" data-i18n="save">Зберегти</button><p id="status" class="form-status"></p></form>
    <hr><h2 data-i18n="profile">Профіль</h2><form id="profileForm"><div class="field"><label for="nickname" data-i18n="nickname">Нікнейм</label><input id="nickname" name="nickname" value="{username}" maxlength="30" required></div><div class="field"><label for="avatarFile" data-i18n="avatarLabel">Аватарка</label><input id="avatarFile" name="avatar" type="file" accept="image/png,image/jpeg,image/webp,image/gif"></div><button class="button ghost" data-i18n="save">Зберегти</button><p id="profileStatus" class="form-status"></p></form>
    </div></main>
    <script>(async()=>{{const f=document.getElementById('settingsForm'),s=await (await fetch('/api/settings')).json();f.language.value=s.language;f.theme.value=s.theme;f.onsubmit=async e=>{{e.preventDefault();const x=Object.fromEntries(new FormData(f));const r=await fetch('/api/settings',{{method:'PATCH',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(x)}});if(r.ok){{localStorage.setItem('origin-language',x.language);localStorage.setItem('origin-theme',x.theme);document.body.classList.toggle('dark',x.theme==='dark');document.getElementById('status').textContent='Збережено';}}}};const pf=document.getElementById('profileForm');pf.onsubmit=async e=>{{e.preventDefault();const file=document.getElementById('avatarFile').files[0];let avatar=null;if(file)avatar=await new Promise(resolve=>{{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.readAsDataURL(file)}});const r=await fetch('/profile',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{nickname:document.getElementById('nickname').value.trim(),avatar}})}});const x=await r.json();document.getElementById('profileStatus').textContent=x.message||x.detail||'Збережено';}}}})();</script>
    """
    return HTMLResponse(_app_page(session, content).replace("</style>", ".settings-page{display:grid;place-items:center;min-height:70vh}.settings-card{width:min(100%,530px);padding:30px;border:1px solid var(--line);border-radius:20px;background:var(--surface);box-shadow:var(--shadow)}.settings-card h1{margin:5px 0 8px;font-size:34px;letter-spacing:-1px}.settings-card form{margin-top:28px}.settings-card hr{border:0;border-top:1px solid var(--line);margin:28px 0}.settings-card h2{font-size:20px}</style>"))


@router.get("/api/settings")
async def get_settings(request: Request):
    return _session(request)["settings"]


@router.patch("/api/settings")
async def update_settings(request: Request):
    session = _session(request)
    payload = await _json(request)
    language = payload.get("language", session["settings"].get("language", "uk"))
    theme = payload.get("theme", session["settings"].get("theme", "dark"))
    if language not in {"uk", "en"} or theme not in {"light", "dark"}:
        raise HTTPException(status_code=422, detail="Непідтримуване налаштування.")
    session["settings"] = {"language": language, "theme": theme}
    return session["settings"]


@router.get("/api/friends")
async def list_friends(request: Request):
    session = _session(request)
    return {"friends": [_friend_json(friend) for friend in session["friends"]]}


@router.post("/api/friends/invite")
async def create_friend_invite(request: Request):
    session = _session(request)
    _ensure_social_fields(session)
    return {
        "link": f"{str(request.base_url).rstrip('/')}/friends/join?token="
        f"{urllib.parse.quote(session['friend_invite_token'])}",
    }


@router.post("/api/friends/add")
async def add_friend(request: Request):
    session = _session(request)
    payload = await _json(request)
    link = str(payload.get("link", "")).strip()
    parsed = urllib.parse.urlparse(link)
    token = urllib.parse.parse_qs(parsed.query).get("token", [""])[0]
    if not token and link:
        token = link
    return _add_friend_by_token(request, session, token)


def _add_friend_by_token(request: Request, session: Dict[str, Any], token: str):
    owner_result = _find_session_by_invite(token)
    if not owner_result:
        raise HTTPException(status_code=404, detail="Посилання на друга недійсне.")
    owner_session_id, owner = owner_result
    current_id = _session_identity(session)
    owner_id = _session_identity(owner)
    if not current_id or current_id == owner_id:
        raise HTTPException(status_code=422, detail="Не можна додати самого себе.")

    _ensure_social_fields(session)
    _ensure_social_fields(owner)
    if not any(friend.get("id") == owner_id for friend in session["friends"]):
        session["friends"].append({
            "id": owner_id,
            "username": owner.get("username", "Користувач"),
            "avatar_url": owner.get("avatar_url", ""),
            "added_at": _now(),
        })
    if not any(friend.get("id") == current_id for friend in owner["friends"]):
        owner["friends"].append({
            "id": current_id,
            "username": session.get("username", "Користувач"),
            "avatar_url": session.get("avatar_url", ""),
            "added_at": _now(),
        })
    _save_session(owner_session_id, owner)
    return {"friend": _friend_json(session["friends"][-1]), "friends": [_friend_json(friend) for friend in session["friends"]]}


@router.get("/friends/join", response_class=HTMLResponse)
async def friend_join(request: Request, token: Optional[str] = None):
    session = _optional_session(request)
    if not session:
        return RedirectResponse("/login", status_code=303)
    if not token:
        return RedirectResponse("/dashboard", status_code=303)
    try:
        _add_friend_by_token(request, session, token)
    except HTTPException:
        return RedirectResponse("/dashboard?friends_error=1", status_code=303)
    return RedirectResponse("/dashboard?friends_added=1", status_code=303)


@router.get("/api/boards")
async def list_boards(request: Request):
    session = _session(request)
    return [{"id": b["id"], "title": b["title"], "description": b["description"], "categories": len(b["categories"])} for b in session["boards"].values()]


@router.post("/api/boards")
async def create_board(request: Request):
    session = _session(request)
    payload = await _json(request)
    title = _text(payload.get("title"), "Назва", 1, 80)
    description = str(payload.get("description", "") or "").strip()[:300]
    board_id = _new_id("board")
    board = {"id": board_id, "title": title, "description": description, "created_at": _now(), "categories": {}, "drawing": []}
    session["boards"][board_id] = board
    return _board_json(board)


@router.get("/api/boards/{board_id}")
async def get_board(request: Request, board_id: str):
    return _board_json(_board(_session(request), board_id))


@router.patch("/api/boards/{board_id}")
async def update_board(request: Request, board_id: str):
    board = _board(_session(request), board_id)
    payload = await _json(request)
    if "title" in payload:
        board["title"] = _text(payload["title"], "Назва", 1, 80)
    if "description" in payload:
        board["description"] = str(payload["description"] or "").strip()[:300]
    return _board_json(board)


@router.delete("/api/boards/{board_id}")
async def delete_board(request: Request, board_id: str):
    session = _session(request)
    _board(session, board_id)
    del session["boards"][board_id]
    return {"ok": True}


@router.post("/api/boards/{board_id}/categories")
async def create_category(request: Request, board_id: str):
    board = _board(_session(request), board_id)
    payload = await _json(request)
    name = _text(payload.get("name"), "Назва колонки", 1, 50)
    category_id = _new_id("cat")
    category = {"id": category_id, "name": name, "color": str(payload.get("color", "#5865f2"))[:20], "width": 340, "position": len(board["categories"]), "cards": {}}
    board["categories"][category_id] = category
    return _category_json(category)


@router.patch("/api/boards/{board_id}/categories/{category_id}")
async def update_category(request: Request, board_id: str, category_id: str):
    category = _category(_board(_session(request), board_id), category_id)
    payload = await _json(request)
    if "name" in payload:
        category["name"] = _text(payload["name"], "Назва колонки", 1, 50)
    if "color" in payload:
        category["color"] = str(payload["color"])[:20]
    if "width" in payload:
        try:
            category["width"] = max(260, min(600, int(payload["width"])))
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="Некоректна ширина категорії.") from exc
    return _category_json(category)


@router.delete("/api/boards/{board_id}/categories/{category_id}")
async def delete_category(request: Request, board_id: str, category_id: str):
    board = _board(_session(request), board_id)
    _category(board, category_id)
    del board["categories"][category_id]
    for position, category in enumerate(sorted(board["categories"].values(), key=lambda x: x["position"])):
        category["position"] = position
    return {"ok": True}


@router.post("/api/boards/{board_id}/categories/{category_id}/cards")
async def create_card(request: Request, board_id: str, category_id: str):
    category = _category(_board(_session(request), board_id), category_id)
    payload = await _json(request)
    title = _text(payload.get("title"), "Назва картки", 1, 120)
    card_id = _new_id("card")
    card = {"id": card_id, "title": title, "description": str(payload.get("description", "") or "").strip()[:5000], "position": len(category["cards"]), "checklist": [], "created_at": _now()}
    category["cards"][card_id] = card
    return card


@router.get("/api/cards/{card_id}")
async def get_card(request: Request, card_id: str):
    return _find_card(_session(request), card_id)[2]


@router.patch("/api/cards/{card_id}")
async def update_card(request: Request, card_id: str):
    card = _find_card(_session(request), card_id)[2]
    payload = await _json(request)
    if "title" in payload:
        card["title"] = _text(payload["title"], "Назва картки", 1, 120)
    if "description" in payload:
        card["description"] = str(payload["description"] or "").strip()[:5000]
    return card


@router.delete("/api/cards/{card_id}")
async def delete_card(request: Request, card_id: str):
    _, category, _ = _find_card(_session(request), card_id)
    del category["cards"][card_id]
    for position, card in enumerate(sorted(category["cards"].values(), key=lambda x: x["position"])):
        card["position"] = position
    return {"ok": True}


@router.post("/api/cards/{card_id}/checklist")
async def add_checklist_item(request: Request, card_id: str):
    card = _find_card(_session(request), card_id)[2]
    payload = await _json(request)
    item = {"id": _new_id("item"), "text": _text(payload.get("text"), "Пункт", 1, 180), "done": False}
    card["checklist"].append(item)
    return item


@router.patch("/api/cards/{card_id}/checklist/{item_id}")
async def update_checklist_item(request: Request, card_id: str, item_id: str):
    card = _find_card(_session(request), card_id)[2]
    item = next((item for item in card["checklist"] if item["id"] == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Пункт не знайдено.")
    payload = await _json(request)
    if "text" in payload:
        item["text"] = _text(payload["text"], "Пункт", 1, 180)
    if "done" in payload:
        item["done"] = bool(payload["done"])
    return item


@router.delete("/api/cards/{card_id}/checklist/{item_id}")
async def delete_checklist_item(request: Request, card_id: str, item_id: str):
    card = _find_card(_session(request), card_id)[2]
    before = len(card["checklist"])
    card["checklist"] = [item for item in card["checklist"] if item["id"] != item_id]
    if len(card["checklist"]) == before:
        raise HTTPException(status_code=404, detail="Пункт не знайдено.")
    return {"ok": True}


@router.get("/api/boards/{board_id}/drawing")
async def get_drawing(request: Request, board_id: str):
    return {"drawing": _board(_session(request), board_id).get("drawing", [])}


@router.put("/api/boards/{board_id}/drawing")
async def save_drawing(request: Request, board_id: str):
    board = _board(_session(request), board_id)
    payload = await _json(request)
    drawing = payload.get("drawing", [])
    if not isinstance(drawing, list) or len(drawing) > 500:
        raise HTTPException(status_code=422, detail="Некоректний малюнок.")
    clean = []
    for stroke in drawing:
        if not isinstance(stroke, list) or len(stroke) > 2000:
            raise HTTPException(status_code=422, detail="Некоректний малюнок.")
        points = []
        for point in stroke:
            if not isinstance(point, list) or len(point) != 2:
                raise HTTPException(status_code=422, detail="Некоректний малюнок.")
            try:
                points.append([max(0, min(5000, float(point[0]))), max(0, min(5000, float(point[1])))])
            except (TypeError, ValueError) as exc:
                raise HTTPException(status_code=422, detail="Некоректний малюнок.") from exc
        clean.append(points)
    board["drawing"] = clean
    return {"drawing": clean}


@router.get("/auth/logout")
async def logout(request: Request):
    session_id = request.cookies.get(SESSION_COOKIE)
    if session_id:
        session = _load_session(session_id)
        if session:
            session["active"] = False
            _save_session(session_id, session)
        request.state.origin_session_deleted = True
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response
