from fastapi import FastAPI, Request, Query, HTTPException, UploadFile, File
from fastapi.responses import PlainTextResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import hmac
import hashlib
import os
import time
import uuid

from .config import VERIFY_TOKEN, APP_SECRET, UPLOAD_DIR, PUBLIC_BASE_URL, REQUIRED_SCOPES
from . import instagram_client as ig
from . import oauth
from .db import (
    init_db, get_conn, log_activity, get_account, save_account, clear_account,
)
from .rules_engine import find_matching_reply

app = FastAPI(title="LimbuAI Instagram Automation Dashboard")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Dashboard data endpoints
# ---------------------------------------------------------------------------

@app.get("/api/profile")
def api_profile():
    try:
        return ig.get_profile()
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/media")
def api_media(limit: int = 12):
    try:
        return ig.get_media(limit=limit)
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/media/{media_id}/insights")
def api_media_insights(media_id: str):
    try:
        return ig.get_media_insights(media_id)
    except Exception as e:
        # Some media types don't support all metrics — fall back to reach only
        try:
            return ig.get_media_insights(media_id, metrics="reach")
        except Exception as e2:
            raise HTTPException(500, str(e2))


@app.get("/api/media/{media_id}/comments")
def api_media_comments(media_id: str):
    try:
        return ig.get_comments(media_id)
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/comments/{comment_id}/reply")
def api_reply_comment(comment_id: str, payload: dict):
    message = payload.get("message", "")
    if not message:
        raise HTTPException(400, "message is required")
    try:
        result = ig.reply_to_comment(comment_id, message)
        log_activity("manual_comment_reply", f"comment_id={comment_id} message={message}")
        return result
    except Exception as e:
        log_activity("manual_comment_reply", str(e), status="failed")
        raise HTTPException(500, str(e))


@app.post("/api/comments/{comment_id}/hide")
def api_hide_comment(comment_id: str, payload: dict):
    hide = payload.get("hide", True)
    try:
        result = ig.hide_comment(comment_id, hide=hide)
        log_activity("manual_hide_comment", f"comment_id={comment_id} hide={hide}")
        return result
    except Exception as e:
        log_activity("manual_hide_comment", str(e), status="failed")
        raise HTTPException(500, str(e))


@app.delete("/api/comments/{comment_id}")
def api_delete_comment(comment_id: str):
    try:
        result = ig.delete_comment(comment_id)
        log_activity("manual_delete_comment", f"comment_id={comment_id}")
        return result
    except Exception as e:
        log_activity("manual_delete_comment", str(e), status="failed")
        raise HTTPException(500, str(e))


# ---------------------------------------------------------------------------
# Auto-reply rules management (comments)
# ---------------------------------------------------------------------------

@app.get("/api/rules/comments")
def list_comment_rules():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM comment_rules ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]


@app.post("/api/rules/comments")
def create_comment_rule(payload: dict):
    keyword = payload.get("keyword")
    reply_text = payload.get("reply_text")
    match_type = payload.get("match_type", "contains")
    if not keyword or not reply_text:
        raise HTTPException(400, "keyword and reply_text are required")
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO comment_rules (keyword, reply_text, match_type) VALUES (?, ?, ?)",
            (keyword, reply_text, match_type),
        )
        conn.commit()
    return {"status": "created"}


@app.delete("/api/rules/comments/{rule_id}")
def delete_comment_rule(rule_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM comment_rules WHERE id = ?", (rule_id,))
        conn.commit()
    return {"status": "deleted"}


# ---------------------------------------------------------------------------
# Auto-reply rules management (DMs)
# ---------------------------------------------------------------------------

@app.get("/api/rules/dms")
def list_dm_rules():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM dm_rules ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]


@app.post("/api/rules/dms")
def create_dm_rule(payload: dict):
    keyword = payload.get("keyword")
    reply_text = payload.get("reply_text")
    match_type = payload.get("match_type", "contains")
    if not keyword or not reply_text:
        raise HTTPException(400, "keyword and reply_text are required")
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO dm_rules (keyword, reply_text, match_type) VALUES (?, ?, ?)",
            (keyword, reply_text, match_type),
        )
        conn.commit()
    return {"status": "created"}


@app.delete("/api/rules/dms/{rule_id}")
def delete_dm_rule(rule_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM dm_rules WHERE id = ?", (rule_id,))
        conn.commit()
    return {"status": "deleted"}


# ---------------------------------------------------------------------------
# Activity log
# ---------------------------------------------------------------------------

@app.get("/api/activity")
def api_activity(limit: int = 50):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM activity_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Instagram Business Login (OAuth)
# This is the flow Meta's App Review screencasts must open with.
# ---------------------------------------------------------------------------

def _redirect_uri(request: Request) -> str:
    """Callback URL for this deployment - must match the App Dashboard entry."""
    base = PUBLIC_BASE_URL or str(request.base_url).rstrip("/")
    return f"{base}/auth/callback"


@app.get("/api/auth/status")
def auth_status(request: Request):
    account = get_account()
    status = {
        "connected": bool(account),
        "app_configured": oauth.is_configured(),
        "scopes": REQUIRED_SCOPES,
        "redirect_uri": _redirect_uri(request),
    }
    if account:
        status["ig_user_id"] = account.get("ig_user_id")
        status["username"] = account.get("username")
        status["source"] = account.get("source", "login")
        expires_at = account.get("expires_at")
        if expires_at:
            status["expires_in_days"] = max(0, round((expires_at - time.time()) / 86400))
    return status


@app.get("/auth/login")
def auth_login(request: Request):
    """Send the user to Instagram's permission screen."""
    try:
        return RedirectResponse(oauth.build_authorize_url(_redirect_uri(request)))
    except oauth.OAuthError as e:
        raise HTTPException(500, str(e))


@app.get("/auth/callback")
def auth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
):
    """Instagram redirects here after the user presses Allow (or Cancel)."""
    if error:
        log_activity("login", error_description or error, status="failed")
        return RedirectResponse(f"/?login_error={error_description or error}")
    if not code:
        return RedirectResponse("/?login_error=No authorization code was returned")
    if not oauth.consume_state(state):
        return RedirectResponse("/?login_error=Login session expired, please try again")

    redirect_uri = _redirect_uri(request)
    try:
        short = oauth.exchange_code(code, redirect_uri)
        long_lived = oauth.exchange_for_long_lived(short["access_token"])
    except oauth.OAuthError as e:
        log_activity("login", str(e), status="failed")
        return RedirectResponse(f"/?login_error={e}")

    token = long_lived["access_token"]
    expires_in = long_lived.get("expires_in")
    ig_user_id = str(short.get("user_id") or "")
    save_account(ig_user_id=ig_user_id, access_token=token, expires_in=expires_in)

    # Now that a token is stored, fill in the username for the header.
    try:
        profile = ig.get_profile()
        save_account(
            ig_user_id=profile.get("id", ig_user_id),
            access_token=token,
            expires_in=expires_in,
            username=profile.get("username"),
        )
        log_activity("login", "connected @" + str(profile.get("username")))
    except Exception as e:
        log_activity("login", f"token saved but profile fetch failed: {e}", status="failed")

    return RedirectResponse("/?login=success")


@app.post("/api/auth/logout")
def auth_logout():
    clear_account()
    log_activity("logout", "account disconnected")
    return {"status": "disconnected"}


@app.post("/api/auth/refresh")
def auth_refresh():
    """Extend the long-lived token by another 60 days."""
    account = get_account()
    if not account:
        raise HTTPException(400, "No account connected")
    try:
        data = oauth.refresh_long_lived(account["access_token"])
    except oauth.OAuthError as e:
        raise HTTPException(500, str(e))
    save_account(
        ig_user_id=account["ig_user_id"],
        access_token=data["access_token"],
        expires_in=data.get("expires_in"),
        username=account.get("username"),
    )
    log_activity("token_refresh", "long-lived token extended")
    return {"status": "refreshed", "expires_in": data.get("expires_in")}


# ---------------------------------------------------------------------------
# Content publishing (instagram_business_content_publish)
# ---------------------------------------------------------------------------

ALLOWED_IMAGE_TYPES = {"image/jpeg": ".jpg", "image/jpg": ".jpg", "image/png": ".png"}
MAX_UPLOAD_BYTES = 8 * 1024 * 1024


@app.post("/api/upload")
async def api_upload(request: Request, file: UploadFile = File(...)):
    """Store an image locally and hand back a public URL that Instagram can fetch.

    Instagram downloads the image itself, so this URL must be reachable from the
    internet - on localhost, paste an already-hosted image URL instead.
    """
    ext = ALLOWED_IMAGE_TYPES.get((file.content_type or "").lower())
    if not ext:
        raise HTTPException(400, "Only JPEG and PNG images can be published to Instagram")
    body = await file.read()
    if len(body) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, "Image is larger than 8 MB")

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    name = f"{uuid.uuid4().hex}{ext}"
    with open(os.path.join(UPLOAD_DIR, name), "wb") as f:
        f.write(body)

    base = PUBLIC_BASE_URL or str(request.base_url).rstrip("/")
    return {"image_url": f"{base}/uploads/{name}", "filename": name}


@app.post("/api/publish")
def api_publish(payload: dict):
    """Create a media container, wait for it to finish processing, then publish it."""
    image_url = (payload.get("image_url") or "").strip()
    caption = payload.get("caption", "")
    if not image_url:
        raise HTTPException(400, "image_url is required")
    if not image_url.startswith(("http://", "https://")):
        raise HTTPException(400, "image_url must be a public http(s) URL")

    try:
        container = ig.create_media_container(image_url=image_url, caption=caption)
        creation_id = container.get("id")
        if not creation_id:
            raise ig.InstagramAPIError("Instagram did not return a media container id")

        # Instagram processes the image asynchronously; wait for FINISHED.
        for _ in range(15):
            status = ig.get_container_status(creation_id)
            code = status.get("status_code")
            if code == "FINISHED":
                break
            if code in ("ERROR", "EXPIRED"):
                raise ig.InstagramAPIError(
                    "Instagram could not process this image "
                    f"({status.get('status', code)})"
                )
            time.sleep(2)

        result = ig.publish_media(creation_id)
        log_activity("publish_post", f"media_id={result.get('id')} caption={caption[:120]}")
        return {"status": "published", "media_id": result.get("id")}
    except ig.InstagramAPIError as e:
        log_activity("publish_post", str(e), status="failed")
        raise HTTPException(500, str(e))


@app.get("/api/publish/limit")
def api_publish_limit():
    try:
        return ig.get_publishing_limit()
    except ig.InstagramAPIError as e:
        raise HTTPException(500, str(e))


# ---------------------------------------------------------------------------
# Webhook: this is what makes auto-reply real-time.
# Point your Meta App's webhook URL to: https://your-domain.com/webhook
# ---------------------------------------------------------------------------

@app.get("/webhook")
def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
):
    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        return PlainTextResponse(hub_challenge)
    raise HTTPException(403, "Verification failed")


def _verify_signature(raw_body: bytes, signature_header: str | None) -> bool:
    if not APP_SECRET:
        return True  # skip check if no secret configured (dev mode)
    if not signature_header:
        return False
    expected = "sha256=" + hmac.new(APP_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)


@app.post("/webhook")
async def receive_webhook(request: Request):
    raw_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    if not _verify_signature(raw_body, signature):
        raise HTTPException(403, "Invalid signature")

    payload = await request.json()
    log_activity("webhook_received", str(payload)[:500])

    for entry in payload.get("entry", []):
        # --- Comments ---
        for change in entry.get("changes", []):
            if change.get("field") == "comments":
                value = change.get("value", {})
                comment_id = value.get("id")
                comment_text = value.get("text", "")
                reply = find_matching_reply(comment_text, "comment_rules")
                if reply and comment_id:
                    try:
                        ig.reply_to_comment(comment_id, reply)
                        log_activity("auto_comment_reply", f"comment_id={comment_id} reply={reply}")
                    except Exception as e:
                        log_activity("auto_comment_reply", str(e), status="failed")

        # --- Direct Messages ---
        for messaging_event in entry.get("messaging", []):
            sender_id = messaging_event.get("sender", {}).get("id")
            message = messaging_event.get("message", {})
            text = message.get("text", "")
            reply = find_matching_reply(text, "dm_rules")
            if reply and sender_id:
                try:
                    ig.send_dm_reply(sender_id, reply)
                    log_activity("auto_dm_reply", f"sender_id={sender_id} reply={reply}")
                except Exception as e:
                    log_activity("auto_dm_reply", str(e), status="failed")

    return JSONResponse({"status": "ok"})


# ---------------------------------------------------------------------------
# Serve the dashboard frontend
# ---------------------------------------------------------------------------
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
