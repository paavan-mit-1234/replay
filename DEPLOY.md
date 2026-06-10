# Deploying Replay (Render + Vercel + Supabase)

Supabase is already hosted. You deploy two things: the API (Render) and the
dashboard (Vercel). Do them in this order so each has the URL it needs.

The two secrets you will paste come straight from your local `replay/.env`:
- `REPLAY_DATABASE_URL` (the replay_app pooler connection string)
- `REPLAY_VAULT_KEY` (must match local exactly, or stored provider keys cannot be decrypted)

---

## 1. Push to GitHub (you do this)

Create a new private repo on GitHub, then from `C:\Users\paava\replay`:

```
git remote add origin https://github.com/<you>/replay.git
git push -u origin main
```

---

## 2. Deploy the API on Render

1. Go to https://render.com, sign up (no card needed), connect your GitHub.
2. New + -> **Blueprint** -> pick the `replay` repo. Render reads `render.yaml`
   and proposes a free web service named `replay-api`. (Or: New + -> Web Service
   -> the repo -> Runtime **Docker**.)
3. Before the first deploy, set the secret env vars (Environment tab):
   - `REPLAY_DATABASE_URL` = the value from your local `.env`
   - `REPLAY_VAULT_KEY` = the value from your local `.env`
   - `REPLAY_CORS_ORIGINS` = leave as `*` for now; you will tighten it in step 4
4. Deploy. When it is live you get a URL like
   `https://replay-api-xxxx.onrender.com`. Open `/health` on it to confirm
   `{"status":"ok",...}`. Copy this API URL.

Note: the Render free tier sleeps after ~15 minutes idle, so the first request
after a nap takes ~50 seconds to wake. Fine for a demo.

---

## 3. Deploy the dashboard on Vercel

1. Go to https://vercel.com, sign up, connect GitHub, **Import** the `replay` repo.
2. Set **Root Directory** to `web` (the framework auto-detects as Vite).
3. Add Environment Variables:
   - `VITE_SUPABASE_URL` = `https://zlctyusgfmiveiymovvk.supabase.co`
   - `VITE_SUPABASE_ANON_KEY` = the anon key from your local `web/.env`
   - `VITE_REPLAY_API_URL` = the Render API URL from step 2 (no trailing slash)
4. Deploy. You get a URL like `https://replay-xxx.vercel.app`. Copy it.

---

## 4. Wire CORS and Supabase to the dashboard URL

1. Render: set `REPLAY_CORS_ORIGINS` = your Vercel URL (e.g.
   `https://replay-xxx.vercel.app`). Save; Render redeploys.
2. Supabase dashboard -> Authentication -> URL Configuration:
   - Site URL = your Vercel URL
   - Redirect URLs: add your Vercel URL (and keep `http://localhost:5173` for
     local dev)
3. For email/password signup to work instantly, turn OFF "Confirm email" under
   Authentication -> Providers -> Email (or leave it on and confirm via email).
4. For Google sign-in, add a Google Cloud OAuth client and paste the client id
   and secret into Authentication -> Providers -> Google.

---

## 5. Done

Visit your Vercel URL, sign up, add a provider key in Settings, create a Replay
API key, and either use the Playground or point any app's `base_url` at
`https://replay-api-xxxx.onrender.com/v1`. No terminals, no localhost.

## Notes
- Schema migrations run as the database owner, not `replay_app`. The schema is
  already applied to Supabase; future migrations are applied out of band (not by
  the running API), so the container only ever serves traffic.
- Keep `REPLAY_VAULT_KEY` identical between local and production. It decrypts the
  BYOK provider keys stored in the shared database.
