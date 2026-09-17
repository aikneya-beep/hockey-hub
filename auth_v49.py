from __future__ import annotations

import hashlib
import hmac
import html
import os
import secrets
import time
from collections import defaultdict
from urllib.parse import quote, urlparse

import psycopg
from fastapi import Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse

import app_v05 as core
from design_system_v46 import COMMON_CSS, topbar

COOKIE_NAME = "hh_session"
SESSION_DAYS = 30
PBKDF2_ITERATIONS = 600_000

_AUTH_SCHEMA = """
create table if not exists personal_hockey_auth (
    singleton smallint primary key default 1 check (singleton = 1),
    password_hash text not null,
    updated_at timestamptz not null default now()
)
"""


class AuthStore:
    def __init__(self) -> None:
        self.database_url = (os.getenv("DATABASE_URL") or "").strip()
        self._schema_ready = False

    def _connect(self):
        if not self.database_url:
            raise RuntimeError("DATABASE_URL is not configured")
        return psycopg.connect(self.database_url, connect_timeout=8)

    def _ensure(self, conn) -> None:
        if self._schema_ready:
            return
        conn.execute(_AUTH_SCHEMA)
        self._schema_ready = True

    def get_password_hash(self) -> str | None:
        with self._connect() as conn:
            self._ensure(conn)
            row = conn.execute(
                "select password_hash from personal_hockey_auth where singleton=1"
            ).fetchone()
            conn.commit()
        return row[0] if row else None

    def set_password_hash(self, value: str) -> None:
        with self._connect() as conn:
            self._ensure(conn)
            conn.execute(
                """insert into personal_hockey_auth(singleton,password_hash,updated_at)
                values(1,%s,now())
                on conflict(singleton) do update set password_hash=excluded.password_hash,updated_at=now()""",
                (value,),
            )
            conn.commit()


STORE = AuthStore()
_ATTEMPTS: dict[str, list[float]] = defaultdict(list)


def _esc(value) -> str:
    return html.escape(str(value or ""))


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(18)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str | None) -> bool:
    if not encoded:
        return False
    try:
        algorithm, iterations, salt_hex, digest_hex = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, int(iterations)
        )
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def _session_secret() -> bytes:
    value = (os.getenv("AUTH_SESSION_SECRET") or "").strip()
    if len(value) < 32:
        raise RuntimeError("AUTH_SESSION_SECRET is not configured")
    return value.encode("utf-8")


def make_session_token(now: int | None = None) -> str:
    issued = int(now or time.time())
    expires = issued + SESSION_DAYS * 86400
    nonce = secrets.token_urlsafe(12)
    payload = f"v1.{expires}.{nonce}"
    signature = hmac.new(_session_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def verify_session_token(token: str | None, now: int | None = None) -> bool:
    if not token:
        return False
    try:
        version, expires_raw, nonce, signature = token.split(".", 3)
        if version != "v1" or not nonce:
            return False
        expires = int(expires_raw)
        if expires < int(now or time.time()):
            return False
        payload = f"{version}.{expires}.{nonce}"
        expected = hmac.new(_session_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)
    except Exception:
        return False


def _safe_next(value: str | None) -> str:
    text = (value or "").strip()
    if text.startswith("/my-hockey") and not text.startswith("//"):
        return text
    return "/my-hockey"


def _same_origin(request: Request) -> bool:
    host = (request.headers.get("host") or "").lower()
    origin = request.headers.get("origin")
    referer = request.headers.get("referer")
    for raw in (origin, referer):
        if not raw:
            continue
        try:
            parsed = urlparse(raw)
            return parsed.netloc.lower() == host
        except Exception:
            return False
    return False


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


def _rate_limited(key: str) -> bool:
    now = time.time()
    attempts = [stamp for stamp in _ATTEMPTS[key] if stamp > now - 900]
    _ATTEMPTS[key] = attempts
    return len(attempts) >= 6


def _record_failure(key: str) -> None:
    _ATTEMPTS[key].append(time.time())


def _clear_failures(key: str) -> None:
    _ATTEMPTS.pop(key, None)


def _auth_page(*, mode: str, message: str = "", next_path: str = "/my-hockey") -> str:
    setup = mode == "setup"
    title = "Настроить закрытый раздел" if setup else "Войти в Мой хоккей"
    subtitle = (
        "Первичная настройка выполняется один раз. Пароль будет сохранён только как стойкий хэш."
        if setup
        else "Личные тренировки, заметки, прогресс и хоккейный шкаф доступны только после входа."
    )
    message_html = f'<div class="auth-message">{_esc(message)}</div>' if message else ""
    if setup:
        fields = '''
        <label>Одноразовый код настройки<input name="setup_token" autocomplete="one-time-code" required></label>
        <label>Новый пароль<input type="password" name="password" autocomplete="new-password" minlength="10" required></label>
        <label>Повтори пароль<input type="password" name="password_confirm" autocomplete="new-password" minlength="10" required></label>
        '''
        action = "/setup"
        button = "Закрыть Мой хоккей паролем"
    else:
        fields = '<label>Пароль<input type="password" name="password" autocomplete="current-password" autofocus required></label>'
        action = "/login"
        button = "Войти"
    return f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title} · Hockey Hub</title><meta name="theme-color" content="#05070b"><style>
{COMMON_CSS}
body{{background:radial-gradient(circle at 78% 0%,rgba(42,134,217,.12),transparent 28%),#05070b}}
.auth-wrap{{min-height:calc(100vh - 72px);display:grid;place-items:center;padding:42px 0}}.auth-card{{width:min(100%,470px);background:linear-gradient(180deg,#10151c,#090d12);border:1px solid #293440;border-radius:20px;padding:28px;box-shadow:0 28px 90px rgba(0,0,0,.35)}}.auth-kicker{{color:#6e8baa;font-size:10px;text-transform:uppercase;letter-spacing:.16em}}.auth-card h1{{font-size:34px;line-height:1.02;margin:10px 0 10px;letter-spacing:-.025em}}.auth-card>p{{color:#8e99a8;font-size:13px;line-height:1.55;margin:0 0 24px}}.auth-message{{padding:11px 12px;border:1px solid #603840;background:#1a1014;color:#e6abb2;border-radius:10px;font-size:11px;margin-bottom:14px}}label{{display:grid;gap:7px;color:#97a3b2;font-size:10px;margin-top:13px}}input{{width:100%;border:1px solid #2a3542;border-radius:10px;background:#090d12;color:#f3f5f8;padding:12px 13px;outline:none}}input:focus{{border-color:#2a86d9;box-shadow:0 0 0 2px rgba(42,134,217,.12)}}button{{width:100%;margin-top:20px;border:1px solid #aab6c3;border-radius:10px;background:#dbe1e7;color:#0b0e12;padding:12px;font-weight:800;cursor:pointer}}.auth-foot{{margin-top:16px;color:#667484;font-size:9px;line-height:1.5}}.auth-foot a{{color:#91a9c1}}
</style></head><body><main class="hub-shell">{topbar('mine')}<section class="auth-wrap"><article class="auth-card"><div class="auth-kicker">PRIVATE AREA · BLACK / SILVER / SOYUZ BLUE</div><h1>{title}</h1><p>{subtitle}</p>{message_html}<form method="post" action="{action}">{fields}<input type="hidden" name="next_path" value="{_esc(next_path)}"><button type="submit">{button}</button></form><div class="auth-foot">Сессия сохраняется на этом браузере до 30 дней. Cookie — Secure / HttpOnly / SameSite.</div></article></section></main></body></html>'''


def _set_session(response: RedirectResponse) -> None:
    response.set_cookie(
        COOKIE_NAME,
        make_session_token(),
        max_age=SESSION_DAYS * 86400,
        secure=True,
        httponly=True,
        samesite="lax",
        path="/",
    )


_PROTECTED_EXACT = {"/refresh", "/debug", "/docs", "/redoc", "/openapi.json"}


@core.app.middleware("http")
async def private_area_guard(request: Request, call_next):
    path = request.url.path
    protected = path.startswith("/my-hockey") or path in _PROTECTED_EXACT
    authenticated = verify_session_token(request.cookies.get(COOKIE_NAME))

    if protected and not authenticated:
        if request.method in {"GET", "HEAD"}:
            destination = path
            if request.url.query:
                destination += "?" + request.url.query
            return RedirectResponse("/login?next=" + quote(_safe_next(destination), safe="/?:=&"), status_code=303)
        return RedirectResponse("/login?next=/my-hockey", status_code=303)

    if protected and request.method not in {"GET", "HEAD", "OPTIONS"}:
        if not _same_origin(request):
            return PlainTextResponse("CSRF check failed", status_code=403)

    return await call_next(request)


@core.app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "/my-hockey"):
    if verify_session_token(request.cookies.get(COOKIE_NAME)):
        return RedirectResponse(_safe_next(next), status_code=303)
    try:
        configured = STORE.get_password_hash() is not None
    except Exception as exc:
        return HTMLResponse(_auth_page(mode="login", message=f"Хранилище авторизации недоступно: {type(exc).__name__}"), status_code=503)
    if not configured:
        return RedirectResponse("/setup", status_code=303)
    return _auth_page(mode="login", next_path=_safe_next(next))


@core.app.post("/login")
def login_submit(request: Request, password: str = Form(...), next_path: str = Form("/my-hockey")):
    key = _client_key(request)
    if _rate_limited(key):
        return HTMLResponse(_auth_page(mode="login", message="Слишком много попыток. Попробуй через 15 минут.", next_path=_safe_next(next_path)), status_code=429)
    try:
        encoded = STORE.get_password_hash()
    except Exception as exc:
        return HTMLResponse(_auth_page(mode="login", message=f"Хранилище авторизации недоступно: {type(exc).__name__}", next_path=_safe_next(next_path)), status_code=503)
    if not verify_password(password, encoded):
        _record_failure(key)
        return HTMLResponse(_auth_page(mode="login", message="Неверный пароль.", next_path=_safe_next(next_path)), status_code=401)
    _clear_failures(key)
    response = RedirectResponse(_safe_next(next_path), status_code=303)
    _set_session(response)
    return response


@core.app.get("/setup", response_class=HTMLResponse)
def setup_page(request: Request):
    try:
        if STORE.get_password_hash() is not None:
            return RedirectResponse("/login", status_code=303)
    except Exception as exc:
        return HTMLResponse(_auth_page(mode="setup", message=f"PostgreSQL недоступен: {type(exc).__name__}"), status_code=503)
    if not (os.getenv("AUTH_SETUP_TOKEN") or "").strip():
        return HTMLResponse(_auth_page(mode="setup", message="Одноразовый код настройки не задан на сервере."), status_code=503)
    return _auth_page(mode="setup")


@core.app.post("/setup")
def setup_submit(
    request: Request,
    setup_token: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    next_path: str = Form("/my-hockey"),
):
    try:
        if STORE.get_password_hash() is not None:
            return RedirectResponse("/login", status_code=303)
    except Exception as exc:
        return HTMLResponse(_auth_page(mode="setup", message=f"PostgreSQL недоступен: {type(exc).__name__}"), status_code=503)

    expected = (os.getenv("AUTH_SETUP_TOKEN") or "").strip()
    if not expected or not hmac.compare_digest(setup_token.strip(), expected):
        return HTMLResponse(_auth_page(mode="setup", message="Неверный одноразовый код настройки."), status_code=401)
    if password != password_confirm:
        return HTMLResponse(_auth_page(mode="setup", message="Пароли не совпадают."), status_code=400)
    if len(password) < 10:
        return HTMLResponse(_auth_page(mode="setup", message="Пароль должен быть не короче 10 символов."), status_code=400)
    if password.casefold() in {"password123", "hockey12345", "1234567890"}:
        return HTMLResponse(_auth_page(mode="setup", message="Этот пароль слишком очевидный."), status_code=400)

    try:
        STORE.set_password_hash(hash_password(password))
    except Exception as exc:
        return HTMLResponse(_auth_page(mode="setup", message=f"Не удалось сохранить пароль: {type(exc).__name__}"), status_code=503)

    response = RedirectResponse(_safe_next(next_path), status_code=303)
    _set_session(response)
    return response


@core.app.post("/logout")
def logout(request: Request):
    if not _same_origin(request):
        return PlainTextResponse("CSRF check failed", status_code=403)
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(COOKIE_NAME, path="/")
    return response
