# Hosting this app on the internet

## Why not Vercel?

[Vercel](https://vercel.com) is built for **serverless** and **static** front ends. This project is a **Flask** app that:

- Accepts **large PDF uploads**
- Runs **PyMuPDF** (native code) on the server
- Uses **local disk** for `data/bank.json`

On Vercel, functions are short-lived, have tight limits, and **no durable local disk** between invocations. You would need a rewrite (e.g. Next.js + object storage + a worker) to run safely there.

**Recommended:** [Render](https://render.com) or [Railway](https://railway.app) — they run a normal Python web process and work well with this codebase.

---

## Option A: Render (free tier)

1. Push this repo to GitHub.
2. In Render: **New → Blueprint** (or **Web Service**).
3. Connect the repo; Render will detect `render.yaml` or use:
   - **Build:** `pip install -r requirements.txt`
   - **Start:** `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120`
4. Deploy. Open the URL Render gives you.

**Note:** On the free tier, **disk is ephemeral** — the question bank file may reset when the service restarts or redeploys. For a class demo that is often fine; for persistence across restarts, add Render Disk or move storage to a database / S3.

---

## Option B: Railway

1. Push to GitHub.
2. [Railway](https://railway.app) → **New Project** → **Deploy from GitHub** → select the repo.
3. Railway detects the `Procfile` and sets `$PORT` automatically.
4. Generate a public domain under **Settings → Networking**.

Same caveat as Render about ephemeral filesystem on hobby tiers unless you add a volume.

---

## Local production-style run

```bash
cd /path/to/mooc
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export PORT=8080
gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120
```

---

## Security

- Do **not** set `FLASK_DEBUG=1` in production.
- Put the app behind HTTPS (Render/Railway provide this).
