# Deploying

## Quickest route: Render (backend) + Vercel (website)

Both build from your GitHub repository, so first get this code onto GitHub (merge the pull request, or deploy the branch).
You need an account on each. Total time: about 20 minutes, most of it waiting for the first build.

**1. Backend on Render**
1. Render dashboard, New, Web Service, connect the repository. Language: **Docker**. Dockerfile path: `./Dockerfile`.
2. Instance type: pick one with **at least 2 GB of RAM** (the price is shown in the dashboard). Free instances go to sleep after
   15 minutes without traffic, take about a minute to wake, and Render says they are not for production; the free tier's RAM is not
   stated in the documentation we read, and the backend likely needs more than a small instance.
3. Advanced: **Health Check Path** `/api/health`.
4. Environment variables:
   - `OPENAI_API_KEY`: a **new** key (with a spend limit set at OpenAI).
   - `API_SHARED_SECRET`: a long random string, for example the output of `openssl rand -hex 32`. Keep a copy: Vercel needs the same value.
5. Create the service and wait for the build. Then open `https://<your-service>.onrender.com/api/health`: it should say `"status":"ok"`.

**2. Website on Vercel**
1. Vercel, Add New, Project, import the same repository. **Root Directory: `web`**. Framework: Next.js (detected).
2. Environment variables (set them **before** the first deploy; `API_URL` is read at build time):
   - `API_URL`: the Render address, for example `https://<your-service>.onrender.com` (no trailing slash)
   - `API_SHARED_SECRET`: the same string as on Render
   - `BASIC_AUTH_USER` and `BASIC_AUTH_PASSWORD`: the login you will give your team
3. Deploy, open the address, sign in, ask a question.

**3. Check it is closed**
- `curl -X POST https://<your-service>.onrender.com/api/chat -H 'content-type: application/json' -d '{"question":"hi"}'` must
  answer **401**. Only the website can ask questions.
- The website asks for the login before showing anything. If a chat says "not signed in, or the keys do not match", the two
  `API_SHARED_SECRET` values differ.

Notes: Vercel's free Hobby plan is for personal, non-commercial use, and its own password protection is a paid Pro feature, which
is why the login lives in the app (`web/proxy.ts`). On Vercel a missing login makes the site refuse to start; it never opens up.

## Or host everything yourself

The rest of this page runs both halves on one Linux server you control.

Two containers on any Linux server, built from open-source pieces (Docker, Docker Compose, Caddy):

```
browser ──HTTPS──> web (Caddy)  ── /api/* ──> api (FastAPI + Chroma + local embedding model) ──> OpenAI
                   serves the site,           not published to the internet;
                   asks for a password,       the knowledge base and its vector
                   gets the HTTPS certificate database are baked into the image
```

Conversations live in each user's browser, so the server keeps no data: nothing to back up.

## What you need

- A Linux server with **Docker Engine and the Compose plugin** ([install guide](https://docs.docker.com/engine/install/)). 1 GB of RAM is the
  minimum we would try, 2 GB is comfortable. Any provider works: a cheap VPS, a cloud VM (for example AWS EC2), a spare machine.
- A **new** OpenAI API key with a monthly spend limit set in the OpenAI dashboard (a leaked or pasted key must be rotated).
- For HTTPS on your own address: a domain name whose DNS `A` record points at the server, and ports 80 and 443 open.

## Steps

1. **Firewall.** Allow only SSH (22), 80 and 443. The API is not published, only the web container is.
2. **Get the code** on the server and enter the folder: `git clone <repo-url> && cd Experiments-`
3. **Create the settings file:**
   ```bash
   cp .env.example .env && chmod 600 .env
   docker run --rm -it caddy caddy hash-password        # type a password; copy the hash it prints
   ```
   Edit `.env`:
   - `OPENAI_API_KEY=` the new key
   - `SITE_ADDRESS=chat.example.com` (your domain; leave `:80` only for testing over plain HTTP)
   - `BASIC_AUTH_USER=` the login name, and `BASIC_AUTH_HASH='...'` the hash, **inside single quotes** (it contains `$` characters)
4. **Start it:** `docker compose up -d --build`. The first build takes a few minutes (about 450 MB of Python packages and an
   80 MB embedding model are downloaded and baked into the image).
5. **Check it:** `docker compose ps` shows `api` as healthy and `web` as running; open the address, log in, ask a question.
   `docker compose logs -f api` shows the API's log.

**Update:** `git pull && docker compose up -d --build`. The vector database is built into the image, so **rebuild after any
change to the knowledge base**.

## No public IP or open ports: Cloudflare Tunnel (free)

Run the site privately and let a tunnel reach it. Cloudflare's free plan includes Access for up to 50 users, who log in with
an emailed code.

1. In `.env` set `WEB_BIND=127.0.0.1` and keep `SITE_ADDRESS=:80` (Cloudflare provides the HTTPS). Start with `docker compose up -d --build`.
2. In the Cloudflare dashboard (Zero Trust, Networks, Tunnels) create a tunnel, run the connector command it shows on the server,
   and add a public hostname that points to `http://localhost:80`.
3. Add an Access application for that hostname with a policy that allows your teammates' email addresses.

The password prompt from Caddy stays on, so people log in twice; that is the safe default.

## Keep the cost under control

Every question costs OpenAI tokens (roughly a cent or two; measure your own usage in the dashboard) and the app has **no rate
limit of its own**. So:
- set the spend limit on the OpenAI key, and
- keep the login on; do not remove `basic_auth` from `web/Caddyfile`.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `docker compose up` stops with "set BASIC_AUTH_HASH in .env" | The hash is empty. Generate it (step 3). |
| Browser shows 401 / keeps asking for the password | Wrong user or password; or the hash was not in single quotes and `$` parts were lost. |
| Site loads but answers fail with a "couldn't complete" message | `docker compose logs api`: usually a wrong or missing `OPENAI_API_KEY`, or the key's limit is reached. |
| 502 from the site | The `api` container is not healthy yet or crashed: `docker compose ps`, then its logs. Out of memory needs a bigger server. |
| No HTTPS certificate | DNS does not point at the server yet, or ports 80/443 are blocked. `docker compose logs web`. |

## Not covered yet

- No rate limiting or daily cap in the app: the login, the API secret and the OpenAI spend limit are what protect the bill.
- One instance only: fine for a team, not for public traffic.
- The Docker files (and the Render and Vercel steps) were written and checked piece by piece (static site build, and the API started with only its runtime
  dependencies), but a full `docker compose build` had not been run when this was written. Treat the first run as a test.
