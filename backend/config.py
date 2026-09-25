import os
from dotenv import load_dotenv

load_dotenv()

# ---- Fill these in your .env file (see .env.example) ----

# Instagram App credentials (Meta App Dashboard -> Instagram -> API setup with
# Instagram business login -> "Instagram app ID" / "Instagram app secret").
IG_APP_ID = os.getenv("IG_APP_ID", "")
IG_APP_SECRET = os.getenv("IG_APP_SECRET", "")

# Where Meta sends the user back after they press "Allow". This exact URL must
# also be listed under "OAuth redirect URIs" in the App Dashboard.
# e.g. https://dashboard.limbuai.com/auth/callback
IG_REDIRECT_URI = os.getenv("IG_REDIRECT_URI", "http://localhost:8000/auth/callback")

# Optional manual fallback: if you already have a long-lived token you can paste
# it here and the dashboard works without anyone logging in. Once a user logs in
# through the UI, the token stored in the database wins over this one.
IG_ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN", "")
IG_USER_ID = os.getenv("IG_USER_ID", "")

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "limbuai_verify_123")
APP_SECRET = os.getenv("APP_SECRET", "")  # optional, for webhook signature check

GRAPH_API_VERSION = "v23.0"
GRAPH_API_BASE = f"https://graph.instagram.com/{GRAPH_API_VERSION}"

# OAuth endpoints for "Instagram API with Instagram Login"
IG_AUTHORIZE_URL = "https://www.instagram.com/oauth/authorize"
IG_TOKEN_URL = "https://api.instagram.com/oauth/access_token"
IG_LONG_LIVED_URL = "https://graph.instagram.com/access_token"
IG_REFRESH_URL = "https://graph.instagram.com/refresh_access_token"

# Vercel's filesystem is read-only except /tmp (which is not persistent).
ON_VERCEL = bool(os.getenv("VERCEL"))
DB_PATH = os.getenv("DB_PATH", "/tmp/ig_dashboard.db" if ON_VERCEL else "ig_dashboard.db")

# Optional: Turso (SQLite-compatible, remote) database. When both are set, the
# app uses Turso instead of a local SQLite file — needed on serverless hosts
# like Vercel where the local filesystem doesn't persist between requests.
# Get these from `turso db show <db-name> --url` and `turso db tokens create <db-name>`.
TURSO_DATABASE_URL = os.getenv("TURSO_DATABASE_URL", "")
TURSO_AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN", "")

# Folder where images uploaded for publishing are stored. Instagram must be able
# to download the image over a public URL, so these are served at /uploads/<file>.
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/tmp/uploads" if ON_VERCEL else "uploads")

# Public base URL of this deployment, used to build the image_url that Instagram
# fetches when publishing. Falls back to the incoming request's own host.
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")

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
    "instagram_business_content_publish",  # create and publish posts from the dashboard
]
