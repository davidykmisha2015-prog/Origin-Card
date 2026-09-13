# -*- coding: utf-8 -*-
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
try:
    from .backend import persist_request_session, router as auth_router
except ImportError:
    from backend import persist_request_session, router as auth_router

app = FastAPI(title="Origin")

# Підключаємо маршрути авторизації з backend.py
app.include_router(auth_router)


@app.middleware("http")
async def save_origin_session(request, call_next):
    response = await call_next(request)
    persist_request_session(request)
    return response

PAGE = r"""<!doctype html>
<html lang="uk">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Origin — простір для ідей</title>
  <style>
    :root { --ink:#17212b; --muted:#667085; --blue:#5865f2; --cyan:#dff7f3; --cream:#fffaf2; --line:#e7e9ef; --surface:#fff; --soft:#f1f1f6; --column:#e6e7ee; }
    body.dark { --ink:#f4f6fb; --muted:#a8b0c0; --blue:#7d86ff; --cyan:#173c3b; --cream:#11151d; --line:#2a3140; --surface:#1a202b; --soft:#202735; --column:#2a3140; }
    * { box-sizing:border-box; }
    html { scroll-behavior:smooth; }
    body { margin:0; color:var(--ink); font-family:Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background:var(--cream); transition:background .25s,color .25s; }
    a { color:inherit; text-decoration:none; }
    .wrap { width:min(1160px, calc(100% - 40px)); margin:auto; }
    nav { height:76px; display:flex; align-items:center; justify-content:space-between; }
    .brand { display:flex; align-items:center; gap:10px; font-size:22px; font-weight:800; letter-spacing:-.7px; }
    .mark { width:31px; height:31px; display:grid; place-items:center; border-radius:10px; color:white; background:var(--blue); box-shadow:7px 7px 0 #cfd2ff; transform:rotate(-6deg); }
    .nav-links { display:flex; gap:30px; color:#566070; font-size:14px; font-weight:600; }
    .dark .nav-links, .dark .login { color:#a8b0c0; }
    .nav-actions { display:flex; align-items:center; gap:15px; font-size:14px; font-weight:700; }
    .icon-button, .language { border:1px solid var(--line); border-radius:10px; padding:9px 10px; color:var(--ink); background:var(--surface); font:inherit; cursor:pointer; }
    .language { padding:9px 8px; }
    .login { color:#566070; }
    .button { border:0; border-radius:12px; padding:13px 19px; font:inherit; cursor:pointer; transition:.2s ease; }
    .button:hover { transform:translateY(-2px); box-shadow:0 10px 20px #5865f22b; }
    .primary { color:white; background:var(--blue); }
    .ghost { color:var(--ink); background:var(--surface); border:1px solid var(--line); }
    .hero { display:grid; grid-template-columns: .9fr 1.1fr; align-items:center; gap:60px; padding:70px 0 96px; }
    .eyebrow { display:inline-flex; align-items:center; gap:8px; padding:7px 11px; border-radius:99px; color:#4b55ca; background:#eceeff; font-size:12px; font-weight:800; letter-spacing:.4px; text-transform:uppercase; }
    .dot { width:7px; height:7px; border-radius:50%; background:#39c78a; }
    h1 { margin:20px 0 18px; max-width:570px; font-size:clamp(46px, 6vw, 75px); line-height:.98; letter-spacing:-4px; }
    .accent { color:var(--blue); }
    .hero-copy { max-width:500px; color:var(--muted); font-size:18px; line-height:1.6; }
    .hero-actions { display:flex; gap:12px; margin-top:29px; }
    .note { margin-top:16px; color:#8b93a3; font-size:12px; }
    .board-shell { padding:16px; border:1px solid var(--line); border-radius:25px; background:var(--soft); box-shadow:20px 24px 60px #28345c1c; transform:rotate(2deg); }
    .board-top { display:flex; align-items:center; justify-content:space-between; padding:2px 7px 14px; color:#717887; font-size:11px; font-weight:700; }
    .board-top b { color:var(--ink); font-size:14px; }
    .mini-actions { display:flex; gap:5px; }
    .mini-dot { width:7px; height:7px; border-radius:50%; background:#d4d7df; }
    .columns { display:grid; grid-template-columns:repeat(3, 1fr); gap:11px; }
    .column { min-height:250px; padding:10px; border-radius:14px; background:var(--column); }
    .column h3 { margin:1px 2px 10px; font-size:11px; }
    .count { float:right; color:#989dab; font-weight:500; }
    .card { margin:8px 0; padding:11px; border-radius:10px; color:#404754; background:var(--surface); box-shadow:0 2px 3px #1b263d0b; font-size:11px; line-height:1.4; }
    .card strong { display:block; margin-bottom:9px; font-size:12px; }
    .tag { display:inline-block; width:27px; height:5px; border-radius:5px; background:#f1a6a0; }
    .tag.green { background:#65cfad; } .tag.yellow { background:#f5ce68; }
    .avatars { display:flex; margin-top:10px; }
    .avatar { width:19px; height:19px; display:grid; place-items:center; margin-right:-4px; border:2px solid white; border-radius:50%; color:white; background:#e48d83; font-size:8px; }
    .avatar:nth-child(2) { background:#7a91dd; } .avatar:nth-child(3) { background:#85bc89; }
    .section { padding:76px 0; background:var(--surface); }
    .section-head { display:flex; justify-content:space-between; align-items:end; margin-bottom:35px; }
    .section h2 { max-width:490px; margin:10px 0 0; font-size:40px; line-height:1.05; letter-spacing:-2px; }
    .section-head p { max-width:300px; margin:0; color:var(--muted); font-size:14px; line-height:1.6; }
    .features { display:grid; grid-template-columns:repeat(3,1fr); gap:18px; }
    .feature { padding:25px; border:1px solid var(--line); border-radius:18px; }
    .icon { width:42px; height:42px; display:grid; place-items:center; margin-bottom:20px; border-radius:13px; color:#4b55ca; background:#eceeff; font-size:20px; }
    .feature h3 { margin:0 0 9px; font-size:17px; } .feature p { margin:0; color:var(--muted); font-size:14px; line-height:1.6; }
    .cta { margin:75px auto; padding:60px; border-radius:25px; text-align:center; background:var(--cyan); }
    .cta h2 { margin:0 auto 13px; font-size:40px; letter-spacing:-2px; } .cta p { margin:0 auto 25px; color:#536d70; }
    footer { padding:26px 0 35px; color:#89919d; font-size:12px; }
    @media (max-width:850px) { .nav-links { display:none; } .hero { grid-template-columns:1fr; gap:42px; padding-top:40px; } .board-shell { transform:none; } .section-head { display:block; } .section-head p { margin-top:20px; } }
    @media (max-width:600px) { .wrap { width:min(100% - 28px, 1160px); } .login { display:none; } h1 { letter-spacing:-2.5px; } .hero-actions { flex-direction:column; } .columns { gap:6px; } .column { padding:7px; } .card { padding:8px; } .cta { padding:38px 20px; } .cta h2, .section h2 { font-size:32px; } .features { grid-template-columns:1fr; } .language { display:none; } }
  </style>
</head>
<body>
  <header class="wrap">
    <nav>
      <a class="brand" href="#"><span class="mark">✦</span> origin</a>
      <div class="nav-links"><a href="#features" data-i18n="features">Можливості</a><a href="#about" data-i18n="how">Як це працює</a><a href="#pricing" data-i18n="pricing">Ціни</a></div>
      <div class="nav-actions"><select class="language" aria-label="Language" onchange="setLanguage(this.value)"><option value="uk">Українська</option><option value="en">English</option><option value="ru">Русский</option><option value="pl">Polski</option></select><button class="icon-button" aria-label="Toggle dark theme" onclick="toggleTheme()">☾</button><a class="login" href="/login" data-i18n="login">Увійти</a><button class="button primary" onclick="start()" data-i18n="try">Спробувати безкоштовно</button></div>
    </nav>
  </header>
  <main>
    <section class="wrap hero">
      <div>
        <span class="eyebrow"><span class="dot"></span> <span data-i18n="eyebrow">твій простір для ідей</span></span>
        <h1 data-i18n="headline">Плануй менше.<br><span class="accent">Створюй більше.</span></h1>
        <p class="hero-copy" data-i18n="copy">Origin допомагає командам організувати роботу, побачити головне й довести кожну ідею до результату.</p>
        <div class="hero-actions"><button class="button primary" onclick="start()" data-i18n="create">Створити дошку безкоштовно →</button><button class="button ghost" onclick="document.querySelector('#features').scrollIntoView()" data-i18n="learn">Дізнатися більше</button></div>
        <div class="note" data-i18n="note">Без картки · Без прихованих платежів · Назавжди безкоштовно</div>
      </div>
      <div class="board-shell" aria-label="Демонстрація дошки">
        <div class="board-top"><b>Запуск продукту <span style="color:#a0a5b0">·</span> <span style="color:#8991a0">Q4</span></b><div class="mini-actions"><span class="mini-dot"></span><span class="mini-dot"></span><span class="mini-dot"></span></div></div>
        <div class="columns">
          <div class="column"><h3>ІДЕЇ <span class="count">3</span></h3><div class="card"><span class="tag yellow"></span><strong>Дослідити аудиторію</strong><small>✨ 4 нотатки</small></div><div class="card"><span class="tag"></span><strong>Нова назва для бренду</strong><small>💬 2 коментарі</small></div></div>
          <div class="column"><h3>У РОБОТІ <span class="count">2</span></h3><div class="card"><span class="tag green"></span><strong>Прототип головної</strong><div class="avatars"><span class="avatar">M</span><span class="avatar">O</span></div></div><div class="card"><span class="tag"></span><strong>Зібрати відгуки</strong><small>↗ 60%</small></div></div>
          <div class="column"><h3>ГОТОВО <span class="count">4</span></h3><div class="card"><span class="tag green"></span><strong>Цінності команди</strong><small>✓ завершено</small></div><div class="card"><span class="tag yellow"></span><strong>План релізу</strong><small>✓ завершено</small></div></div>
        </div>
      </div>
    </section>
    <section class="section" id="features">
      <div class="wrap"><div class="section-head"><div><span class="eyebrow" data-i18n="forAll">для команд і соло</span><h2 data-i18n="sectionTitle">Все, що потрібно,<br>нічого зайвого.</h2></div><p data-i18n="sectionCopy">Простий інструмент, який не заважає думати, а допомагає рухатися вперед.</p></div>
        <div class="features"><article class="feature"><div class="icon">↗</div><h3 data-i18n="feature1Title">Візуальний фокус</h3><p data-i18n="feature1Copy">Розклади завдання по поличках і завжди бач, що наступне.</p></article><article class="feature"><div class="icon">⌁</div><h3 data-i18n="feature2Title">Разом — краще</h3><p data-i18n="feature2Copy">Додавай людей, обговорюй ідеї та створюй результат командою.</p></article><article class="feature"><div class="icon">♡</div><h3 data-i18n="feature3Title">Безкоштовно назавжди</h3><p data-i18n="feature3Copy">Жодних пробних періодів і сюрпризів. Основні функції — для всіх.</p></article></div>
      </div>
    </section>
    <section class="wrap cta" id="pricing"><h2 data-i18n="ctaTitle">Твоя наступна<br>велика ідея — тут.</h2><p data-i18n="ctaCopy">Почни за хвилину. Рости у своєму темпі.</p><button class="button primary" onclick="start()" data-i18n="start">Почати безкоштовно →</button></section>
  </main>
  <footer class="wrap">© 2026 Origin Cards <span style="float:right">Створено для ясних думок.</span></footer>
  <script>
    const i18n = {
      uk: { features:'Можливості', how:'Як це працює', pricing:'Ціни', login:'Увійти', try:'Спробувати безкоштовно', eyebrow:'твій простір для ідей', headline:'Плануй менше.<br><span class="accent">Створюй більше.</span>', copy:'Origin допомагає командам організувати роботу, побачити головне й довести кожну ідею до результату.', create:'Створити дошку безкоштовно →', learn:'Дізнатися більше', note:'Без картки · Без прихованих платежів · Назавжди безкоштовно', forAll:'для команд і соло', sectionTitle:'Все, що потрібно,<br>нічого зайвого.', sectionCopy:'Простий інструмент, який не заважає думати, а допомагає рухатися вперед.', feature1Title:'Візуальний фокус', feature1Copy:'Розклади завдання по поличках і завжди бач, що наступне.', feature2Title:'Разом — краще', feature2Copy:'Додавай людей, обговорюй ідеї та створюй результат командою.', feature3Title:'Безкоштовно назавжди', feature3Copy:'Жодних пробних періодів і сюрпризів. Основні функції — для всіх.', ctaTitle:'Твоя наступна<br>велика ідея — тут.', ctaCopy:'Почни за хвилину. Рости у своєму темпі.', start:'Почати безкоштовно →', toast:'Чудово! Створення дошки буде доступне зовсім скоро ✦' },
      en: { features:'Features', how:'How it works', pricing:'Pricing', login:'Sign in', try:'Try for free', eyebrow:'your space for ideas', headline:'Plan less.<br><span class="accent">Create more.</span>', copy:'Origin helps teams organize work, see what matters, and turn every idea into a result.', create:'Create a free board →', learn:'Learn more', note:'No card · No hidden fees · Free forever', forAll:'for teams and solo makers', sectionTitle:'Everything you need,<br>nothing you do not.', sectionCopy:'A simple tool that helps you move forward without getting in the way.', feature1Title:'Visual focus', feature1Copy:'Keep tasks organized and always know what comes next.', feature2Title:'Better together', feature2Copy:'Invite people, discuss ideas, and create results as a team.', feature3Title:'Free forever', feature3Copy:'No trials or surprises. Core features are available to everyone.', ctaTitle:'Your next<br>big idea starts here.', ctaCopy:'Get started in a minute. Grow at your own pace.', start:'Start for free →', toast:'Great! Board creation will be available very soon ✦' },
      ru: { features:'Возможности', how:'Как это работает', pricing:'Цены', login:'Войти', try:'Попробовать бесплатно', eyebrow:'твоё пространство для идей', headline:'Планируй меньше.<br><span class="accent">Создавай больше.</span>', copy:'Origin помогает командам организовать работу, увидеть главное и довести каждую идею до результата.', create:'Создать доску бесплатно →', learn:'Узнать больше', note:'Без карты · Без скрытых платежей · Навсегда бесплатно', forAll:'для команд и соло', sectionTitle:'Всё необходимое,<br>ничего лишнего.', sectionCopy:'Простой инструмент, который помогает двигаться вперёд и не мешает думать.', feature1Title:'Визуальный фокус', feature1Copy:'Разложи задачи по полочкам и всегда видь следующий шаг.', feature2Title:'Вместе лучше', feature2Copy:'Приглашай людей, обсуждай идеи и создавай результат командой.', feature3Title:'Бесплатно навсегда', feature3Copy:'Без пробных периодов и сюрпризов. Основные функции доступны всем.', ctaTitle:'Твоя следующая<br>большая идея — здесь.', ctaCopy:'Начни за минуту. Расти в своём темпе.', start:'Начать бесплатно →', toast:'Отлично! Создание доски станет доступно совсем скоро ✦' },
      pl: { features:'Możliwości', how:'Jak to działa', pricing:'Cennik', login:'Zaloguj się', try:'Wypróbuj za darmo', eyebrow:'twoja przestrzeń na pomysły', headline:'Planuj mniej.<br><span class="accent">Twórz więcej.</span>', copy:'Origin pomaga zespołom organizować pracę, widzieć to, co ważne, i zamieniać pomysły w rezultaty.', create:'Utwórz darmową tablicę →', learn:'Dowiedz się więcej', note:'Bez karty · Bez ukrytych opłat · Na zawsze za darmo', forAll:'dla zespołów i solistów', sectionTitle:'Wszystko, czego potrzebujesz,<br>nic więcej.', sectionCopy:'Proste narzędzie, które pomaga działać i nie przeszkadza w myśleniu.', feature1Title:'Wizualny fokus', feature1Copy:'Uporządkuj zadania i zawsze wiedz, co jest następne.', feature2Title:'Razem lepiej', feature2Copy:'Dodawaj osoby, omawiaj pomysły i twórzcie rezultaty razem.', feature3Title:'Darmowe na zawsze', feature3Copy:'Bez okresów próbnych i niespodzianek. Najważniejsze funkcje są dla każdego.', ctaTitle:'Twój kolejny<br>wielki pomysł zaczyna się tutaj.', ctaCopy:'Zacznij w minutę. Rozwijaj się we własnym tempie.', start:'Zacznij za darmo →', toast:'Świetnie! Tworzenie tablicy będzie dostępne już wkrótce ✦' }
    };
    let currentLanguage = localStorage.getItem('origin-language') || 'uk';
    function setLanguage(language) { currentLanguage = language; localStorage.setItem('origin-language', language); document.documentElement.lang = language; document.querySelectorAll('[data-i18n]').forEach(el => el.innerHTML = i18n[language][el.dataset.i18n]); }
    function toggleTheme() { document.body.classList.toggle('dark'); localStorage.setItem('origin-theme', document.body.classList.contains('dark') ? 'dark' : 'light'); }
    function toast(text) { const el=document.createElement('div'); el.textContent=text; Object.assign(el.style,{position:'fixed',bottom:'24px',left:'50%',transform:'translateX(-50%)',padding:'13px 18px',borderRadius:'12px',background:'#17212b',color:'#fff',fontSize:'14px',zIndex:5}); document.body.appendChild(el); setTimeout(()=>el.remove(),2400); }
    function start() { toast(i18n[currentLanguage].toast); }
    if (localStorage.getItem('origin-theme') === 'dark') document.body.classList.add('dark');
    document.querySelector('.language').value = currentLanguage;
    setLanguage(currentLanguage);
  </script>
</body>
</html>"""

LOGIN_PAGE = r"""<!doctype html>
<html lang="uk">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Вхід — Origin</title>
  <style>
    * { box-sizing: border-box; }
    :root { --login-bg:#0f131d; --login-ink:#f1f3f9; --login-card:#171c28cc; --login-muted:#9da6ba; }
    body.light { --login-bg:#f7f8fc; --login-ink:#17212b; --login-card:#ffffffdd; --login-muted:#667085; }
    body {
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      background: var(--login-bg);
      color: var(--login-ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, sans-serif;
      overflow: hidden;
    }
    .orb { position: fixed; border-radius: 50%; filter: blur(40px); pointer-events: none; z-index: 0; opacity: 0.5; }
    .orb.one { width: 350px; height: 350px; top: -100px; left: -100px; background: #5865f2; }
    .orb.two { width: 300px; height: 300px; bottom: -80px; right: -80px; background: #39c78a; }

    .login-card {
      position: relative;
      z-index: 1;
      width: min(90%, 400px);
      padding: 40px 32px;
      background: var(--login-card);
      border: 1px solid #ffffff14;
      border-radius: 24px;
      box-shadow: 0 24px 60px rgba(0, 0, 0, 0.4);
      backdrop-filter: blur(10px);
      text-align: center;
    }
    .brand {
      display: inline-flex;
      align-items: center;
      gap: 10px;
      font-size: 24px;
      font-weight: 800;
      color: #fff;
      text-decoration: none;
      margin-bottom: 24px;
      letter-spacing: -0.7px;
    }
    .mark {
      width: 34px;
      height: 34px;
      display: grid;
      place-items: center;
      border-radius: 10px;
      color: white;
      background: #5865f2;
      transform: rotate(-6deg);
    }
    h1 { margin: 0 0 8px; font-size: 22px; letter-spacing: -0.5px; }
    p { margin: 0 0 28px;     color: var(--login-muted); font-size: 14px; line-height: 1.5; }

    .auth-tabs { display:flex; gap:8px; margin:18px 0 12px; }
    .auth-tab { flex:1; padding:10px; border:1px solid #ffffff24; border-radius:10px; color:var(--login-muted); background:transparent; font-weight:700; cursor:pointer; }
    .auth-tab.active { color:#fff; background:#5865f2; border-color:#5865f2; }
    .auth-form { display:none; }
    .auth-form.active { display:block; }
    .auth-form input { width:100%; margin:6px 0; padding:13px; border:1px solid #ffffff24; border-radius:12px; color:var(--login-ink); background:transparent; font:14px inherit; }
    .auth-form button { width:100%; margin-top:8px; padding:13px; border:0; border-radius:12px; color:#fff; background:#5865f2; font-weight:700; cursor:pointer; }
    .auth-status { min-height:18px; margin:9px 0 0; font-size:12px; }
    .back-link {
      display: inline-block;
      margin-top: 24px;
      color: #8b93a3;
      font-size: 13px;
      text-decoration: none;
      transition: color 0.2s;
    }
    .back-link:hover { color: #fff; }
    .theme-toggle { position:fixed; top:20px; right:20px; padding:9px 11px; border:1px solid #ffffff22; border-radius:10px; color:var(--login-ink); background:var(--login-card); cursor:pointer; }
  </style>
</head>
<body>
  <div class="orb one"></div>
  <div class="orb two"></div>
  <button class="theme-toggle" id="themeToggle" aria-label="Змінити тему">☾</button>

  <div class="login-card">
    <a class="brand" href="/"><span class="mark">✦</span> origin</a>
    <h1 id="authTitle">Вхід</h1>
    <p>Увійди або створи акаунт за допомогою email і пароля.</p>

    <div style="display:none">
      <svg height="20" width="20" viewBox="0 0 16 16" fill="currentColor">
        <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.22 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"></path>
      </svg>
      Увійти через GitHub
    </div>
    <div class="auth-tabs"><button class="auth-tab active" data-mode="login">Увійти</button><button class="auth-tab" data-mode="register">Реєстрація</button></div>
    <form class="auth-form active" id="loginForm">
      <input type="email" name="email" placeholder="Email" required>
      <input type="password" name="password" placeholder="Пароль" required>
      <button type="submit">Увійти</button>
    </form>
    <form class="auth-form" id="registerForm">
      <input type="email" name="email" placeholder="Email" required>
      <input type="password" name="password" placeholder="Пароль (мінімум 8 символів)" minlength="8" required>
      <button type="submit">Зареєструватися</button>
    </form>
    <div class="auth-status" id="authStatus"></div>

    <a class="back-link" href="/">← На головну</a>
  </div>
  <script>
    const loginTheme = localStorage.getItem('origin-theme') || 'dark';
    document.body.classList.toggle('light', loginTheme === 'light');
    document.getElementById('themeToggle').onclick = () => {
      const light = !document.body.classList.contains('light');
      document.body.classList.toggle('light', light);
      localStorage.setItem('origin-theme', light ? 'light' : 'dark');
    };
    const status = document.getElementById('authStatus');
    document.querySelectorAll('.auth-tab').forEach(tab => tab.onclick = () => {
      document.querySelectorAll('.auth-tab,.auth-form').forEach(el => el.classList.remove('active'));
      tab.classList.add('active');
      document.getElementById(tab.dataset.mode + 'Form').classList.add('active');
      document.getElementById('authTitle').textContent = tab.dataset.mode === 'login' ? 'Вхід' : 'Реєстрація';
      status.textContent = '';
    });
    async function submitAuth(event, endpoint) {
      event.preventDefault();
      const form = event.currentTarget;
      const response = await fetch(endpoint, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({email:form.email.value.trim(), password:form.password.value})});
      const data = await response.json().catch(() => ({}));
      status.textContent = data.message || data.detail || 'Сталася помилка.';
      if (response.ok && endpoint === '/auth/login') location.href = '/boards';
    }
    document.getElementById('loginForm').onsubmit = event => submitAuth(event, '/auth/login');
    document.getElementById('registerForm').onsubmit = event => submitAuth(event, '/auth/register');
  </script>
</body>
</html>"""

@app.get("/", response_class=HTMLResponse)
async def read_root():
    return PAGE

@app.get("/login", response_class=HTMLResponse)
async def read_login():
    return LOGIN_PAGE
