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
        f'<img id="avatarPreview" class="avatar" src="{avatar_url}" alt="Аватар">'
        if avatar_url
        else '<div id="avatarPreview" class="avatar avatar-fallback">✦</div>'
    )

    return f"""
    <!doctype html>
    <html lang="uk">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>Origin — твій простір</title>
      <style>
        :root {{ color-scheme: dark; }}
        * {{ box-sizing: border-box; }}
        body {{ margin: 0; min-height: 100vh; color: #f4f6fb;
          background: #0f131d; font-family: Inter, ui-sans-serif, system-ui,
          -apple-system, sans-serif; }}
        .page {{ width: min(1080px, calc(100% - 32px)); margin: auto;
          padding: 28px 0 60px; }}
        nav {{ display: flex; align-items: center; justify-content: space-between; }}
        .brand {{ color: #fff; text-decoration: none; font-size: 22px;
          font-weight: 800; }}
        .mark {{ display: inline-grid; width: 31px; height: 31px;
          margin-right: 8px; place-items: center; border-radius: 10px;
          color: #fff; background: #5865f2; transform: rotate(-6deg); }}
        .account {{ position: relative; }}
        .avatar-button {{ width: 48px; height: 48px; padding: 0; border: 0;
          border-radius: 50%; cursor: pointer; background: transparent; }}
        .avatar {{ width: 48px; height: 48px; border: 2px solid #5865f2;
          border-radius: 50%; object-fit: cover; }}
        .avatar-fallback {{ display: grid; place-items: center; color: #fff;
          background: linear-gradient(135deg, #5865f2, #39c78a); font-size: 20px; }}
        .menu {{ position: absolute; top: 60px; right: 0; z-index: 2;
          display: none; min-width: 150px; padding: 8px; border: 1px solid #ffffff14;
          border-radius: 12px; background: #171c28; box-shadow: 0 14px 35px #0008; }}
        .menu.open {{ display: block; }}
        .menu a, .menu button {{ display: block; width: 100%; padding: 10px;
          border: 0; border-radius: 8px; color: #dce1ed; background: transparent;
          text-align: left; text-decoration: none; font: inherit; cursor: pointer; }}
        .menu a:hover, .menu button:hover {{ background: #ffffff10; }}
        .welcome {{ max-width: 720px; margin: 150px auto 0; text-align: center; }}
        .welcome h1 {{ margin: 0 0 14px; font-size: clamp(38px, 7vw, 72px);
          letter-spacing: -3px; }}
        .welcome p {{ margin: 0 0 34px; color: #9da6ba; font-size: 18px; }}
        .create {{ display: inline-block; padding: 15px 24px; border-radius: 12px;
          color: #fff; background: #5865f2; font-weight: 800; text-decoration: none;
          box-shadow: 0 12px 28px #5865f244; }}
        .create:hover {{ background: #6972ff; transform: translateY(-2px); }}
        .modal {{ position: fixed; inset: 0; z-index: 3; display: none;
          place-items: center; padding: 20px; background: #0009; }}
        .modal.open {{ display: grid; }}
        .card {{ width: min(100%, 430px); padding: 28px; border: 1px solid #ffffff14;
          border-radius: 22px; background: #171c28; box-shadow: 0 22px 50px #0008; }}
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
        .close {{ float: right; border: 0; color: #9da6ba; background: transparent;
          font-size: 22px; cursor: pointer; }}
      </style>
    </head>
    <body>
      <div class="page">
        <nav>
          <a class="brand" href="/"><span class="mark">✦</span>origin</a>
          <div class="account">
            <button class="avatar-button" id="avatarButton" aria-label="Профіль">
              {avatar}
            </button>
            <div class="menu" id="accountMenu">
              <button id="editProfile">Редагувати профіль</button>
              <a href="/auth/logout">Вийти</a>
            </div>
          </div>
        </nav>
        <section class="welcome">
          <h1>Вітаємо, {username}! 👋</h1>
          <p>Готовий перетворити ідею на результат?</p>
          <a class="create" href="/boards/new">＋ Створити дошку</a>
        </section>
        <div class="modal" id="profileModal">
          <form class="card" id="profileForm">
            <button class="close" id="closeModal" type="button">×</button>
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
        </div>
      </div>
      <script>
        const form = document.getElementById('profileForm');
        const fileInput = document.getElementById('avatar');
        const preview = document.getElementById('avatarPreview');
        const status = document.getElementById('status');
        const modal = document.getElementById('profileModal');
        const menu = document.getElementById('accountMenu');
        document.getElementById('avatarButton').onclick = () =>
          menu.classList.toggle('open');
        document.getElementById('editProfile').onclick = () => {{
          menu.classList.remove('open');
          modal.classList.add('open');
        }};
        document.getElementById('closeModal').onclick = () =>
          modal.classList.remove('open');
        modal.onclick = (event) => {{
          if (event.target === modal) modal.classList.remove('open');
        }};

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
            document.querySelector('.welcome h1').textContent =
              `Вітаємо, ${{data.username}}! 👋`;
            modal.classList.remove('open');
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


@router.get("/boards/new", response_class=HTMLResponse)
async def new_board(request: Request):
    session_id = request.cookies.get(SESSION_COOKIE)
    if session_id not in sessions:
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(
        """
        <!doctype html>
        <html lang="uk">
        <head>
          <meta charset="utf-8">
          <meta name="viewport" content="width=device-width, initial-scale=1">
          <title>Нова дошка — Origin</title>
          <style>
            body { margin: 0; min-height: 100vh; display: grid; place-items: center;
              color: #f4f6fb; background: #0f131d;
              font-family: Inter, system-ui, sans-serif; text-align: center; }
            .card { width: min(90%, 440px); padding: 34px; border-radius: 22px;
              border: 1px solid #ffffff14; background: #171c28; }
            h1 { margin: 0 0 10px; }
            p { margin: 0 0 24px; color: #9da6ba; }
            a { display: inline-block; padding: 12px 18px; border-radius: 10px;
              color: #fff; background: #5865f2; text-decoration: none;
              font-weight: 700; }
          </style>
        </head>
        <body>
          <div class="card">
            <h1>Нова дошка</h1>
            <p>Робочий простір для твоїх ідей вже майже готовий.</p>
            <a href="/dashboard">← Повернутися на головну</a>
          </div>
        </body>
        </html>
        """
    )


@router.get("/auth/logout")
async def logout(request: Request):
    session_id = request.cookies.get(SESSION_COOKIE)
    if session_id:
        sessions.pop(session_id, None)
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response
