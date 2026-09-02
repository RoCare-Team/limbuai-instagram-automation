# LimbuAI Instagram Automation Dashboard

Ek complete Python (FastAPI) backend + dashboard jo Instagram Business account ke
comments, insights, aur DMs ko manage karta hai — auto-reply rules ke saath.

## Kya-kya ho sakta hai isse

- 🔐 Instagram Business Login — user "Continue with Instagram" dabata hai, permissions allow karta hai, token khud save ho jata hai
- 📊 Profile aur post-level insights (reach, likes, comments, shares, saved)
- 💬 Comments dekhna, manually reply karna, hide/delete karna
- 🤖 Keyword-based auto-reply rules (comments + DMs) — webhook live hote hi automatic chalti hain
- 📤 Dashboard se hi Instagram pe naya post publish karna (image + caption)
- 📜 Activity log — kaun sa auto-reply kab bheja gaya

## 1. Local setup (testing ke liye)

```bash
cd ig-dashboard
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# .env me IG_APP_ID aur IG_APP_SECRET daalo (Meta App Dashboard ->
# Instagram -> API setup with Instagram business login)

uvicorn backend.main:app --reload --port 8000
```

Browser me kholo: **http://localhost:8000**

Login button dabao, permissions allow karo — dashboard, insights, comments, manual reply sab kaam karega.

Localhost pe do cheezein nahi chalengi:
- **Webhook (real-time auto-reply)** — Meta ko public URL chahiye
- **File upload se publishing** — Instagram khud image download karta hai, isliye image URL public hona chahiye. Local pe test karne ke liye koi already-hosted image ka URL paste kar do.

## 2. Live deploy karna (webhook ke liye zaroori)

App ko koi bhi Python host chala sakta hai. Repo me `Procfile` aur `runtime.txt`
already hain, to zyadatar platforms khud detect kar lenge.

- **Build command:** `pip install -r requirements.txt`
- **Start command:** `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
- **Python version:** 3.11 (`runtime.txt` me set hai)

Environment variables (host ke dashboard me daalne hain):

| Variable | Kya daalna hai |
|---|---|
| `IG_APP_ID` | Meta App Dashboard se Instagram app ID |
| `IG_APP_SECRET` | Meta App Dashboard se Instagram app secret |
| `PUBLIC_BASE_URL` | Deploy hone ke baad mila URL, e.g. `https://dashboard.limbuai.com` |
| `VERIFY_TOKEN` | Webhook verify token (jo Meta me bhi daaloge) |
| `APP_SECRET` | Webhook signature verify karne ke liye |
| `DB_PATH` | Writable path, e.g. `/tmp/ig_dashboard.db` |
| `UPLOAD_DIR` | Writable path, e.g. `/tmp/uploads` |

**Dhyan rakhna:** SQLite file aur uploads local disk pe hain. Agar host har deploy pe
disk wipe karta hai to rules aur activity log reset ho jayenge — permanent chahiye to
persistent disk lo ya database Postgres pe move karna padega.

## 3. Meta App me OAuth redirect URI add karo

App Dashboard → **Instagram → API setup with Instagram business login** → "Set up business login" →
**OAuth redirect URIs** me ye daalo:

```
https://<your-deployed-url>/auth/callback
```

Ye bilkul wahi hona chahiye jo `IG_REDIRECT_URI` / `PUBLIC_BASE_URL` se banta hai, warna login "redirect_uri mismatch" error dega.

## 4. Meta App me Webhook connect karo

1. App Dashboard → **Instagram API → Webhooks**
2. Callback URL: `https://<your-deployed-url>/webhook`
3. Verify Token: wahi jo `.env` me `VERIFY_TOKEN` set kiya hai
4. Subscribe karo: **comments**, **messages**

Ab jab bhi koi real comment ya DM aayega jo tumhare rules se match karega, automatically reply jayega.

## 5. Access token ka dhyan rakhna

- `.env` file kabhi bhi GitHub pe public repo me commit mat karna (`.gitignore` me already `.env` add hai)
- Access token kisi ke saath share mat karna
- Login se mila long-lived token 60 din chalta hai; dashboard header se logout/login karke ya
  `POST /api/auth/refresh` se 60 din aur badha sakte ho

## Project structure

```
ig-dashboard/
├── backend/
│   ├── main.py              # FastAPI app, OAuth + publish routes, webhook handler
│   ├── config.py            # environment config
│   ├── oauth.py             # Instagram Business Login flow
│   ├── db.py                # SQLite rules, activity log, saved account token
│   ├── instagram_client.py  # Graph API wrapper (comments, insights, DMs, publishing)
│   ├── rules_engine.py      # keyword matching logic
│   └── static/
│       ├── index.html            # dashboard UI
│       └── app-review-guide.html # Meta App Review walkthrough
├── Procfile                 # start command for any Python host
├── requirements.txt
├── .env.example
└── README.md
```

## Meta App Review

Ye dashboard 5 scopes use karta hai — `instagram_business_basic` (auto-granted) aur
4 jinke liye alag-alag screencast video submit karni padti hai:
`instagram_business_manage_comments`, `instagram_business_manage_messages`,
`instagram_business_manage_insights`, `instagram_business_content_publish`.

Har video me kya dikhana hai, recording ke rules, aur submit checklist —
sab deployed app me hai: **`/app-review-guide.html`**
