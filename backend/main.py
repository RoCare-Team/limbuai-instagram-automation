from fastapi import FastAPI, Request, Query, HTTPException
from fastapi.responses import PlainTextResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import hmac
import hashlib

from .config import VERIFY_TOKEN, APP_SECRET
from . import instagram_client as ig
from .db import init_db, get_conn, log_activity
from .rules_engine import find_matching_reply

app = FastAPI(title="LimbuAI Instagram Automation Dashboard")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()


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
app.mount("/", StaticFiles(directory="backend/static", html=True), name="static")
