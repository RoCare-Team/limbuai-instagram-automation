# LimbuAI Instagram Automation Dashboard

Ek complete Python (FastAPI) backend + dashboard jo Instagram Business account ke
comments, insights, aur DMs ko manage karta hai — auto-reply rules ke saath.

## Kya-kya ho sakta hai isse

- 📊 Profile aur post-level insights (reach, likes, comments, shares, saved)
- 💬 Comments dekhna, manually reply karna, hide/delete karna
- 🤖 Keyword-based auto-reply rules (comments + DMs) — webhook live hote hi automatic chalti hain
- 📜 Activity log — kaun sa auto-reply kab bheja gaya

## 1. Local setup (testing ke liye)

```bash
cd ig-dashboard
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# .env file khol ke apna IG_ACCESS_TOKEN aur IG_USER_ID daalo

uvicorn backend.main:app --reload --port 8000
```

Browser me kholo: **http://localhost:8000**

Is stage pe dashboard, insights, comments, manual reply — sab kaam karega.
Sirf **webhook (real-time auto-reply)** localhost pe nahi chalega — uske liye deploy karna padega (neeche dekho).

## 2. Live deploy karna (webhook ke liye zaroori)

Free options: **Render.com**, **Railway.app**, ya **Fly.io**

### Render.com pe (sabse aasan free option):
1. Is project ko GitHub repo me push karo
2. Render.com pe "New Web Service" banao, apna repo connect karo
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
5. Environment variables me `.env` wali sab values daalo (IG_ACCESS_TOKEN, IG_USER_ID, VERIFY_TOKEN, APP_SECRET)
6. Deploy hone ke baad tumhe ek URL milega jaise `https://limbuai-dashboard.onrender.com`

## 3. Meta App me Webhook connect karo

1. App Dashboard → **Instagram API → Webhooks**
2. Callback URL: `https://<your-deployed-url>/webhook`
3. Verify Token: wahi jo `.env` me `VERIFY_TOKEN` set kiya hai
4. Subscribe karo: **comments**, **messages**

Ab jab bhi koi real comment ya DM aayega jo tumhare rules se match karega, automatically reply jayega.

## 4. Access token ka dhyan rakhna

- `.env` file kabhi bhi GitHub pe public repo me commit mat karna (`.gitignore` me already `.env` add hai)
- Access token kisi ke saath share mat karna
- Token expire ho jaye to naya generate karke `.env` update karo aur server restart/redeploy karo

## Project structure

```
ig-dashboard/
├── backend/
│   ├── main.py              # FastAPI app + webhook handler
│   ├── config.py            # environment config
│   ├── db.py                 # SQLite rules & activity log
│   ├── instagram_client.py  # Graph API wrapper
│   ├── rules_engine.py      # keyword matching logic
│   └── static/
│       └── index.html       # dashboard UI
├── requirements.txt
├── .env.example
└── README.md
```
