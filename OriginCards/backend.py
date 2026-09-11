# -*- coding: utf-8 -*-
import html
import os
import secrets
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

router = APIRouter()

GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")
GITHUB_REDIRECT_URI = os.getenv(
    "GITHUB_REDIRECT_URI",
    "http://localhost:8000/auth/callback",
)
SESSION_COOKIE = "origin_session"
sessions: Dict[str, Dict[str, Any]] = {}


def _check_github_config() -> None:
    if not GITHUB_CLIENT_ID or not GITHUB_CLIENT_SECRET:
        raise HTTPException(
            status_code=503,
            detail=(
                "GitHub OAuth не налаштований: додайте "
                "GITHUB_CLIENT_ID і GITHUB_CLIENT_SECRET."
            ),
        )


def _profile_page(profile: Dict[str, Any]) -> str:
    username = html.escape(profile["username"])
    avatar_url = html.escape(profile.get("avatar_url", ""), quote=True)
    avatar = (
        f'<img id="avatarPreview" src="{avatar_url}" alt="Аватар">'
        if avatar_url
        else '<div id="avatarPreview" class="avatar-fallback">✦</div>'
    )

    return f"""
    <!doctype html>
    <html lang="uk">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>Твій профіль — Origin</title>
      <style>
        :root {{ color-scheme: dark; }}
        * {{ box-sizing: border-box; }}
        body {{ margin: 0; min-height: 100vh; color: #f4f6fb;
          background: #0f131d; font-family: Inter, ui-sans-serif, system-ui,
          -apple-system, sans-serif; }}
        .page {{ width: min(960px, calc(100% - 32px)); margin: auto;
          padding: 28px 0 60px; }}
        nav {{ display: flex; align-items: center; justify-content: space-between;
          margin-bottom: 70px; }}
        .brand {{ color: #fff; text-decoration: none; font-size: 22px;
          font-weight: 800; }}
        .mark {{ display: inline-grid; width: 31px; height: 31px;
          margin-right: 8px; place-items: center; border-radius: 10px;
          color: #fff; background: #5865f2; transform: rotate(-6deg); }}
        .logout {{ padding: 10px 14px; border: 1px solid #ffffff1f;
          border-radius: 10px; color: #a8b0c0; text-decoration: none; }}
        .welcome {{ margin-bottom: 28px; }}
        .welcome h1 {{ margin: 0 0 10px; font-size: clamp(34px, 6vw, 58px);
          letter-spacing: -2px; }}
        .welcome p {{ margin: 0; color: #9da6ba; font-size: 17px; }}
        .layout {{ display: grid; grid-template-columns: .8fr 1.2fr; gap: 22px; }}
        .card {{ padding: 28px; border: 1px solid #ffffff14; border-radius: 22px;
          background: #171c28; box-shadow: 0 22px 50px #0005; }}
        .profile-card {{ display: flex; flex-direction: column; align-items: center;
          justify-content: center; text-align: center; }}
        .avatar-wrap {{ width: 130px; height: 130px; margin-bottom: 20px; }}
        #avatarPreview, .avatar-fallback {{ width: 100%; height: 100%;
          border: 3px solid #5865f2; border-radius: 50%; object-fit: cover; }}
        .avatar-fallback {{ display: grid; place-items: center; color: #fff;
          background: linear-gradient(135deg, #5865f2, #39c78a); font-size: 42px; }}
        .profile-card h2 {{ margin: 0 0 8px; font-size: 24px; }}
        .profile-card p {{ margin: 0; color: #9da6ba; }}
        h3 {{ margin: 0 0 24px; font-size: 21px; }}
        label {{ display: block; margin: 0 0 8px; color: #c9ceda;
          font-size: 14px; font-weight: 700; }}
        input {{ width: 100%; margin-bottom: 20px; padding: 13px 14px;
          border: 1px solid #ffffff1c; border-radius: 11px; outline: none;
          color: #f4f6fb; background: #202735; font: inherit; }}
        input:focus {{ border-color: #5865f2; }}
        input[type=file] {{ padding: 10px; color: #a8b0c0; }}
        .hint {{ margin: -10px 0 22px; color: #7f899d; font-size: 12px; }}
        button {{ width: 100%; padding: 13px 18px; border: 0; border-radius: 11px;
          color: #fff; background: #5865f2; font: inherit; font-weight: 700;
          cursor: pointer; }}
        button:hover {{ background: #6972ff; }}
        #status {{ min-height: 20px; margin-top: 14px; color: #65cfad;
          font-size: 14px; text-align: center; }}
        @media (max-width: 700px) {{ .layout {{ grid-template-columns: 1fr; }}
          nav {{ margin-bottom: 48px; }} }}
      </style>
    </head>
    <body>
      <div class="page">
        <nav>
          <a class="brand" href="/"><span class="mark">✦</span>origin</a>
          <a class="logout" href="/auth/logout">Вийти</a>
        </nav>
        <section class="welcome">
          <h1>Вітаємо, {username}! 👋</h1>
          <p>Це твій простір в Origin. Налаштуй профіль під себе.</p>
        </section>
        <section class="layout">
          <div class="card profile-card">
            <div class="avatar-wrap">{avatar}</div>
            <h2 id="profileName">{username}</h2>
            <p>Твій профіль Origin</p>
          </div>
          <form class="card" id="profileForm">
            <h3>Налаштування профілю</h3>
            <label for="nickname">Нікнейм</label>
            <input id="nickname" name="nickname" value="{username}"
              maxlength="30" required>
            <label for="avatar">Нова аватарка</label>
            <input id="avatar" name="avatar" type="file"
              accept="image/png,image/jpeg,image/webp,image/gif">
            <p class="hint">PNG, JPG, WEBP або GIF. Максимум 5 МБ.</p>
            <button type="submit">Зберегти зміни</button>
            <div id="status" role="status"></div>
          </form>
        </section>
      </div>
      <script>
        const form = document.getElementById('profileForm');
        const fileInput = document.getElementById('avatar');
        const preview = document.getElementById('avatarPreview');
        const status = document.getElementById('status');

        fileInput.addEventListener('change', () => {{
          const file = fileInput.files[0];
          if (!file) return;
          if (file.size > 5 * 1024 * 1024) {{
            fileInput.value = '';
            status.textContent = 'Файл завеликий. Максимум — 5 МБ.';
            status.style.color = '#f1a6a0';
            return;
          }}
          const reader = new FileReader();
          reader.onload = () => {{
            if (preview.tagName === 'IMG') preview.src = reader.result;
            else {{
              const image = document.createElement('img');
              image.id = 'avatarPreview';
              image.alt = 'Аватар';
              image.src = reader.result;
              preview.replaceWith(image);
            }}
          }};
          reader.readAsDataURL(file);
        }});

        form.addEventListener('submit', async (event) => {{
          event.preventDefault();
          const nickname = document.getElementById('nickname').value.trim();
          const file = fileInput.files[0];
          let avatar = null;
          if (file) avatar = await new Promise((resolve) => {{
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result);
            reader.readAsDataURL(file);
          }});
          const response = await fetch('/profile', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ nickname, avatar }})
          }});
          const data = await response.json();
          status.textContent = data.message || data.detail;
          status.style.color = response.ok ? '#65cfad' : '#f1a6a0';
          if (response.ok) {{
            document.getElementById('profileName').textContent = data.username;
            document.querySelector('.welcome h1').textContent =
              `Вітаємо, ${{data.username}}! 👋`;
          }}
        }});
      </script>
    </body>
    </html>
    """


@router.get("/auth/github")
async def github_login():
    _check_github_config()
    params = urlencode(
        {
            "client_id": GITHUB_CLIENT_ID,
            "redirect_uri": GITHUB_REDIRECT_URI,
            "scope": "read:user",
        }
    )
    return RedirectResponse(
        f"https://github.com/login/oauth/authorize?{params}"
    )


@router.get("/auth/callback")
async def github_callback(
    code: Optional[str] = None,
    error: Optional[str] = None,
):
    _check_github_config()
    if error:
        return HTMLResponse(
            f"<h3>Авторизацію скасовано: {html.escape(error)}</h3>",
            status_code=400,
        )
    if not code:
        return HTMLResponse(
            "<h3>GitHub не повернув код авторизації.</h3>",
            status_code=400,
        )

    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            "https://github.com/login/oauth/access_token",
            data={
                "client_id": GITHUB_CLIENT_ID,
                "client_secret": GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": GITHUB_REDIRECT_URI,
            },
            headers={"Accept": "application/json"},
        )
        token_response.raise_for_status()
        token_data = token_response.json()
        access_token = token_data.get("access_token")

        if not access_token:
            error_description = token_data.get(
                "error_description",
                "невідома помилка",
            )
            return HTMLResponse(
                "<h3>Помилка авторизації через GitHub: "
                f"{html.escape(error_description)}</h3>",
                status_code=400,
            )

        user_response = await client.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
            },
        )
        user_response.raise_for_status()
        user_data = user_response.json()

    session_id = secrets.token_urlsafe(32)
    sessions[session_id] = {
        "username": user_data.get("login", "Гість"),
        "avatar_url": user_data.get("avatar_url", ""),
    }
    response = RedirectResponse("/dashboard", status_code=303)
    response.set_cookie(
        SESSION_COOKIE,
        session_id,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
    )
    return response


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    session_id = request.cookies.get(SESSION_COOKIE)
    profile = sessions.get(session_id or "")
    if not profile:
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(_profile_page(profile))


@router.post("/profile")
async def update_profile(request: Request):
    session_id = request.cookies.get(SESSION_COOKIE)
    profile = sessions.get(session_id or "")
    if not profile:
        raise HTTPException(status_code=401, detail="Сесія завершилася. Увійдіть знову.")

    try:
        payload = await request.json()
    except ValueError:
        raise HTTPException(status_code=400, detail="Некоректні дані профілю.")

    nickname = str(payload.get("nickname", "")).strip()
    if not 2 <= len(nickname) <= 30:
        raise HTTPException(
            status_code=422,
            detail="Нікнейм має містити від 2 до 30 символів.",
        )

    avatar = payload.get("avatar")
    if avatar is not None:
        allowed_types = (
            "data:image/png;base64,",
            "data:image/jpeg;base64,",
            "data:image/webp;base64,",
            "data:image/gif;base64,",
        )
        if not isinstance(avatar, str) or not avatar.startswith(allowed_types):
            raise HTTPException(status_code=422, detail="Оберіть коректний файл зображення.")
        if len(avatar) > 7_000_000:
            raise HTTPException(status_code=422, detail="Аватарка завелика. Максимум — 5 МБ.")
        profile["avatar_url"] = avatar

    profile["username"] = nickname
    return JSONResponse({"message": "Профіль оновлено.", "username": nickname})


@router.get("/auth/logout")
async def logout(request: Request):
    session_id = request.cookies.get(SESSION_COOKIE)
    if session_id:
        sessions.pop(session_id, None)
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response
