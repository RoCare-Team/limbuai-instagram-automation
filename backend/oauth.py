"""
"Instagram API with Instagram Login" OAuth flow.

Three hops:
  1. /auth/login    -> redirect the user to Instagram's authorize screen
  2. Instagram      -> user presses "Allow", gets sent back to /auth/callback?code=...
  3. /auth/callback -> swap the code for a short-lived token, then upgrade it to a
                      60-day long-lived token and store it.

This is the flow Meta's reviewers must see at the start of every screencast.
"""
import hashlib
import hmac
import secrets
import time

import httpx

from .config import (
    IG_APP_ID,
    IG_APP_SECRET,
    IG_REDIRECT_URI,
    IG_AUTHORIZE_URL,
    IG_TOKEN_URL,
    IG_LONG_LIVED_URL,
    IG_REFRESH_URL,
    REQUIRED_SCOPES,
)

# CSRF state is a signed, timestamped token (stateless) so it survives serverless
# hosts where /auth/login and /auth/callback may hit different instances.
_STATE_TTL = 600  # seconds


class OAuthError(Exception):
    pass


def is_configured() -> bool:
    return bool(IG_APP_ID and IG_APP_SECRET)


def _sign(payload: str) -> str:
    return hmac.new(IG_APP_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]


def _new_state() -> str:
    payload = f"{int(time.time())}.{secrets.token_urlsafe(12)}"
    return f"{payload}.{_sign(payload)}"


def consume_state(state: str | None) -> bool:
    if not state or not IG_APP_SECRET:
        return False
    payload, _, sig = state.rpartition(".")
    if not payload or not hmac.compare_digest(sig, _sign(payload)):
        return False
    try:
        issued = int(payload.split(".", 1)[0])
    except ValueError:
        return False
    return 0 <= time.time() - issued <= _STATE_TTL


def build_authorize_url(redirect_uri: str | None = None) -> str:
    if not is_configured():
        raise OAuthError(
            "IG_APP_ID and IG_APP_SECRET are not set. Add them to your .env "
            "(Meta App Dashboard -> Instagram -> API setup with Instagram business login)."
        )
    params = {
        "client_id": IG_APP_ID,
        "redirect_uri": redirect_uri or IG_REDIRECT_URI,
        "response_type": "code",
        "scope": ",".join(REQUIRED_SCOPES),
        "state": _new_state(),
    }
    return f"{IG_AUTHORIZE_URL}?{httpx.QueryParams(params)}"


def exchange_code(code: str, redirect_uri: str | None = None) -> dict:
    """Authorization code -> short-lived token (1 hour) + the Instagram user id."""
    # Instagram appends "#_" to the code when it redirects back in a browser.
    code = code.split("#")[0]
    with httpx.Client(timeout=20) as client:
        resp = client.post(IG_TOKEN_URL, data={
            "client_id": IG_APP_ID,
            "client_secret": IG_APP_SECRET,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri or IG_REDIRECT_URI,
            "code": code,
        })
    data = resp.json()
    if "access_token" not in data:
        raise OAuthError(_describe(data, "Could not exchange the login code for a token"))
    return data


def exchange_for_long_lived(short_lived_token: str) -> dict:
    """Short-lived token -> 60-day long-lived token."""
    with httpx.Client(timeout=20) as client:
        resp = client.get(IG_LONG_LIVED_URL, params={
            "grant_type": "ig_exchange_token",
            "client_secret": IG_APP_SECRET,
            "access_token": short_lived_token,
        })
    data = resp.json()
    if "access_token" not in data:
        raise OAuthError(_describe(data, "Could not upgrade to a long-lived token"))
    return data


def refresh_long_lived(token: str) -> dict:
    """Extend a long-lived token for another 60 days (works from day 1)."""
    with httpx.Client(timeout=20) as client:
        resp = client.get(IG_REFRESH_URL, params={
            "grant_type": "ig_refresh_token",
            "access_token": token,
        })
    data = resp.json()
    if "access_token" not in data:
        raise OAuthError(_describe(data, "Could not refresh the token"))
    return data


def _describe(data: dict, fallback: str) -> str:
    err = data.get("error")
    if isinstance(err, dict):
        return err.get("message", fallback)
    if isinstance(err, str):
        return data.get("error_description") or err
    return data.get("error_message") or fallback
