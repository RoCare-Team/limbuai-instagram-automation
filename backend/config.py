import os
from dotenv import load_dotenv

load_dotenv()

# ---- Fill these in your .env file (see .env.example) ----
IG_ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN", "")
IG_USER_ID = os.getenv("IG_USER_ID", "")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "limbuai_verify_123")
APP_SECRET = os.getenv("APP_SECRET", "")  # optional, for webhook signature check

GRAPH_API_VERSION = "v26.0"
GRAPH_API_BASE = f"https://graph.instagram.com/{GRAPH_API_VERSION}"

DB_PATH = os.getenv("DB_PATH", "ig_dashboard.db")

# ---------------------------------------------------------------------------
# Instagram API with Instagram Login — required scopes for this dashboard.
# Request these under Meta App Dashboard -> App Review -> Permissions and
# Features. Each one needs its own description + screencast video.
# See /app-review-guide.html for the full submission walkthrough.
# ---------------------------------------------------------------------------
REQUIRED_SCOPES = [
    "instagram_business_basic",            # profile + media read (auto-granted, no review needed)
    "instagram_business_manage_comments",  # read/reply/hide/delete comments
    "instagram_business_manage_messages",  # send/receive DMs (auto-reply)
    "instagram_business_manage_insights",  # media insights (reach, likes, comments, shares, saved)
]
