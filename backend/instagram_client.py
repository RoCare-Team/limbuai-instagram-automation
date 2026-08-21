"""
Thin wrapper around the Instagram Graph API.
Docs: https://developers.facebook.com/docs/instagram-platform
"""
import httpx
from .config import IG_ACCESS_TOKEN, IG_USER_ID, GRAPH_API_BASE


class InstagramAPIError(Exception):
    pass


def _get(path: str, params: dict | None = None):
    params = params or {}
    params["access_token"] = IG_ACCESS_TOKEN
    url = f"{GRAPH_API_BASE}/{path}"
    with httpx.Client(timeout=15) as client:
        resp = client.get(url, params=params)
    data = resp.json()
    if "error" in data:
        raise InstagramAPIError(data["error"].get("message", "Unknown Instagram API error"))
    return data


def _post(path: str, params: dict | None = None):
    params = params or {}
    params["access_token"] = IG_ACCESS_TOKEN
    url = f"{GRAPH_API_BASE}/{path}"
    with httpx.Client(timeout=15) as client:
        resp = client.post(url, params=params)
    data = resp.json()
    if "error" in data:
        raise InstagramAPIError(data["error"].get("message", "Unknown Instagram API error"))
    return data


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
        resp = client.delete(f"{GRAPH_API_BASE}/{comment_id}", params={"access_token": IG_ACCESS_TOKEN})
    return resp.json()


def send_dm_reply(recipient_id: str, message: str):
    """Send a reply via Instagram Messaging API."""
    url = f"{GRAPH_API_BASE}/{IG_USER_ID}/messages"
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": message},
    }
    with httpx.Client(timeout=15) as client:
        resp = client.post(url, params={"access_token": IG_ACCESS_TOKEN}, json=payload)
    return resp.json()
