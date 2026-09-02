"""
Thin wrapper around the Instagram Graph API.
Docs: https://developers.facebook.com/docs/instagram-platform
"""
import httpx
from .config import GRAPH_API_BASE
from .db import get_account


class InstagramAPIError(Exception):
    pass


class NotConnectedError(InstagramAPIError):
    pass


def _credentials() -> tuple[str, str]:
    """(access_token, ig_user_id) of the connected account."""
    account = get_account()
    if not account or not account.get("access_token"):
        raise NotConnectedError(
            "No Instagram account connected. Click 'Continue with Instagram' to log in."
        )
    # "me" resolves to whichever account the token belongs to, so a stale or
    # missing id in .env can't break publishing or messaging.
    return account["access_token"], account.get("ig_user_id") or "me"


def _token() -> str:
    return _credentials()[0]


def _check(resp: httpx.Response):
    data = resp.json()
    if isinstance(data, dict) and "error" in data:
        raise InstagramAPIError(data["error"].get("message", "Unknown Instagram API error"))
    return data


def _get(path: str, params: dict | None = None):
    params = dict(params or {})
    params["access_token"] = _token()
    with httpx.Client(timeout=15) as client:
        resp = client.get(f"{GRAPH_API_BASE}/{path}", params=params)
    return _check(resp)


def _post(path: str, params: dict | None = None):
    params = dict(params or {})
    params["access_token"] = _token()
    with httpx.Client(timeout=30) as client:
        resp = client.post(f"{GRAPH_API_BASE}/{path}", params=params)
    return _check(resp)


def get_profile():
    return _get("me", {"fields": "id,username,account_type,media_count"})


def get_media(limit: int = 25):
    return _get("me/media", {
        "fields": "id,caption,media_type,media_url,thumbnail_url,permalink,timestamp,like_count,comments_count",
        "limit": limit,
    })


def get_media_insights(media_id: str, metrics: str = "reach,likes,comments,shares,saved"):
    return _get(f"{media_id}/insights", {"metric": metrics})


def get_comments(media_id: str):
    return _get(f"{media_id}/comments", {"fields": "id,text,username,timestamp,like_count"})


def reply_to_comment(comment_id: str, message: str):
    return _post(f"{comment_id}/replies", {"message": message})


def hide_comment(comment_id: str, hide: bool = True):
    return _post(f"{comment_id}", {"hide": str(hide).lower()})


def delete_comment(comment_id: str):
    with httpx.Client(timeout=15) as client:
        resp = client.delete(f"{GRAPH_API_BASE}/{comment_id}", params={"access_token": _token()})
    return _check(resp)


def send_dm_reply(recipient_id: str, message: str):
    """Send a reply via the Instagram Messaging API."""
    token, ig_user_id = _credentials()
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": message},
    }
    with httpx.Client(timeout=15) as client:
        resp = client.post(
            f"{GRAPH_API_BASE}/{ig_user_id}/messages",
            params={"access_token": token},
            json=payload,
        )
    return _check(resp)


# ---------------------------------------------------------------------------
# Content publishing (instagram_business_content_publish)
# Two steps: create a media container, then publish that container.
# ---------------------------------------------------------------------------

def create_media_container(image_url: str, caption: str = "", media_type: str | None = None,
                           video_url: str | None = None):
    token, ig_user_id = _credentials()
    params = {"caption": caption, "access_token": token}
    if media_type == "REELS":
        params["media_type"] = "REELS"
        params["video_url"] = video_url
    else:
        params["image_url"] = image_url
    with httpx.Client(timeout=60) as client:
        resp = client.post(f"{GRAPH_API_BASE}/{ig_user_id}/media", params=params)
    return _check(resp)


def get_container_status(creation_id: str):
    return _get(creation_id, {"fields": "status_code,status"})


def publish_media(creation_id: str):
    token, ig_user_id = _credentials()
    with httpx.Client(timeout=60) as client:
        resp = client.post(
            f"{GRAPH_API_BASE}/{ig_user_id}/media_publish",
            params={"creation_id": creation_id, "access_token": token},
        )
    return _check(resp)


def get_publishing_limit():
    """How many of the 50 posts/24h quota are left."""
    token, ig_user_id = _credentials()
    with httpx.Client(timeout=15) as client:
        resp = client.get(
            f"{GRAPH_API_BASE}/{ig_user_id}/content_publishing_limit",
            params={"fields": "config,quota_usage", "access_token": token},
        )
    return _check(resp)
