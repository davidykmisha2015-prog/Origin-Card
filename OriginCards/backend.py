# -*- coding: utf-8 -*-
import os
import httpx
from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse

router = APIRouter()

# Отримуємо змінні середовища
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")
GITHUB_REDIRECT_URI = os.getenv("GITHUB_REDIRECT_URI")

@router.get("/auth/github")
async def github_login():
    github_auth_url = f"https://github.com/login/oauth/authorize?client_id={GITHUB_CLIENT_ID}&redirect_uri={GITHUB_REDIRECT_URI}&scope=read:user"
    return RedirectResponse(github_auth_url)

@router.get("/auth/callback")
async def github_callback(code: str):
    token_url = "https://github.com/login/oauth/access_token"
    payload = {
        "client_id": GITHUB_CLIENT_ID,
        "client_secret": GITHUB_CLIENT_SECRET,
        "code": code,
        "redirect_uri": GITHUB_REDIRECT_URI
    }
    headers = {"Accept": "application/json"}

    async with httpx.AsyncClient() as client:
        response = await client.post(token_url, data=payload, headers=headers)
        data = response.json()
        access_token = data.get("access_token")

        if not access_token:
            return HTMLResponse("<h3>Помилка авторизації через GitHub!</h3>", status_code=400)

        user_response = await client.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
        )
        user_data = user_response.json()
        username = user_data.get("login", "Гість")
        avatar_url = user_data.get("avatar_url", "")

    return HTMLResponse(f"""
    <!doctype html>
    <html lang="uk">
    <head>
      <meta charset="utf-8">
      <title>Успішний вхід — Origin</title>
      <style>
        body {{ margin: 0; min-height: 100vh; display: grid; place-items: center; background: #0f131d; color: #f1f3f9; font-family: sans-serif; text-align: center; }}
        .card {{ background: #171c28; padding: 40px; border-radius: 20px; border: 1px solid #ffffff14; box-shadow: 0 20px 40px rgba(0,0,0,0.5); }}
        img {{ width: 80px; height: 80px; border-radius: 50%; border: 2px solid #5865f2; margin-bottom: 20px; }}
        h1 {{ margin: 0 0 10px; font-size: 24px; }}
        p {{ color: #9da6ba; margin-bottom: 24px; }}
        a {{ display: inline-block; padding: 12px 24px; background: #5865f2; color: #fff; text-decoration: none; border-radius: 10px; font-weight: bold; }}
      </style>
    </head>
    <body>
      <div class="card">
        <img src="{avatar_url}" alt="Avatar">
        <h1>Вітаємо, {username}!</h1>
        <p>Ти успішно авторизувався через свій GitHub.</p>
        <a href="/">На головну сторінку</a>
      </div>
    </body>
    </html>
    """)
