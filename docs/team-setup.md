# Team setup: working on and deploying the assistant

Three ways a team member can work with this repository after cloning it. Most people only need **A**.

| You want to | Use | You need |
|---|---|---|
| Change the code or knowledge base and release it to the shared server | [A](#a-release-to-the-shared-server) | Write access to the GitHub repository |
| Run the assistant on your own laptop | [B](#b-run-it-on-your-laptop) | Docker Desktop, an OpenAI API key |
| Run your own copy in your own AWS account | [C](#c-your-own-copy-in-your-own-aws-account) | A fork, an AWS account with admin rights, Terraform 1.10+ |

Whichever you choose: **never commit `.env` or any key.** `.env` is git-ignored, and every push runs a secret scan
(gitleaks) that fails the build if a secret gets into the code.

## A. Release to the shared server

The pipeline deploys. You need no AWS keys, no Terraform and no `.env`.

1. Ask the repository owner to add you as a collaborator (GitHub, Settings, Collaborators, role **Write**).
2. Clone and work on a branch:
   ```bash
   git clone https://github.com/josliniyda27/DevOps-AI-Agents-Experiments.git
   cd DevOps-AI-Agents-Experiments
   git switch -c my-change
   # ... make your changes ...
   git push -u origin my-change
   ```
3. Open a pull request to `main`. CI runs the tests, the knowledge-base check, the web checks, Terraform validation and
   the secret scan. Fix anything it reports.
4. When the pull request is merged, the pipeline builds the next `vMAJOR.MINOR.BUILD` release, deploys it to the
   shared server and tags the commit. Follow it under the repository's **Actions** tab. The site address is shown in
   the run summary and under the `production` environment.

To start a new MAJOR or MINOR version, change the `VERSION` file (for example from `0.1` to `0.2`). The build number is added
automatically. See [cicd.md](cicd.md) for how the pipeline works.

**Do not run `deploy/aws/bootstrap` for the shared server.** It is done once per AWS account and is already done; its state
file lives only on the owner's machine. Running it again elsewhere tries to recreate the role and bucket and fails with
"already exists".

## B. Run it on your laptop

You need Docker Desktop (running) and your own OpenAI API key (set a monthly spend limit on it at OpenAI).

1. Clone the repository and create your settings file:
   ```bash
   git clone https://github.com/josliniyda27/DevOps-AI-Agents-Experiments.git
   cd DevOps-AI-Agents-Experiments
   cp .env.example .env          # Windows PowerShell: Copy-Item .env.example .env
   ```
2. Make a login password hash. Type the password you want when asked, and copy the line it prints:
   ```bash
   docker run --rm -it caddy caddy hash-password
   ```
3. Edit `.env`:
   ```
   OPENAI_API_KEY=<your key>
   BASIC_AUTH_USER=team
   BASIC_AUTH_HASH='<the hash, inside single quotes>'
   ```
   and add this line, so the site is only reachable from your own laptop:
   ```
   WEB_BIND=127.0.0.1
   ```
   Keep the single quotes around the hash: it contains `$` characters that Docker Compose would otherwise change.
4. Start it. The first build takes a few minutes, because it downloads Python packages and an embedding model.
   ```bash
   docker compose up -d --build
   ```
5. Open http://localhost and sign in with `team` and your password.

Useful commands:

| What | Command |
|---|---|
| Is it running? | `docker compose ps` (the `api` service should say "healthy") |
| API logs | `docker compose logs -f api` |
| After changing the knowledge base | `docker compose up -d --build` (the vector store is built into the image) |
| Stop it | `docker compose down` |

**Share it for a short session (optional).** With [ngrok](https://ngrok.com) installed and signed in
(`ngrok config add-authtoken <your token>`), run `ngrok http 80`. It prints a public `https://` address that stays
behind your login. It works only while your laptop is on and both Docker and ngrok are running. Stop ngrok afterwards.

**Develop without Docker.** See the Setup section in the [README](../README.md): a Python virtual environment for the API,
and `npm run dev` in `web/` for the UI.

## C. Your own copy in your own AWS account

This creates a separate server, billed to your AWS account. Use an AWS account other than the shared one: the bootstrap's
role and bucket names are fixed per account, so a second copy in the same account would clash.

1. **Fork** the repository on GitHub. Then, in your fork's **Actions** tab, enable workflows.
2. **Load your AWS admin credentials** into your terminal, for example with `aws configure` or environment variables.
   In PowerShell, from a `.env` that holds them:
   ```powershell
   Get-Content .env | Where-Object { $_ -match '^(AWS_ACCESS_KEY_ID|AWS_SECRET_ACCESS_KEY|AWS_DEFAULT_REGION)=' } | ForEach-Object { $k,$v = $_ -split '=',2; Set-Item "env:$k" $v.Trim("'`"") }
   ```
3. **Check how your fork identifies itself to AWS:**
   ```bash
   gh api repos/<your-user>/DevOps-AI-Agents-Experiments/actions/oidc/customization/sub
   ```
   If the answer contains `"use_immutable_subject": true`, copy its `sub_claim_prefix` value. It looks like
   `repo:<your-user>@<number>/DevOps-AI-Agents-Experiments@<number>`.
4. **Create the AWS side once**, from the repository root:
   ```bash
   terraform -chdir=deploy/aws/bootstrap init
   terraform -chdir=deploy/aws/bootstrap apply \
     -var github_repo=<your-user>/DevOps-AI-Agents-Experiments \
     -var region=us-west-2 \
     -var 'github_subject_prefix=<the sub_claim_prefix from step 3>'
   ```
   Leave out the `github_subject_prefix` line if step 3 did not show immutable subjects. If your account already trusts
   GitHub Actions (IAM, Identity providers, `token.actions.githubusercontent.com`), add `-var create_oidc_provider=false`.
   Keep the `terraform.tfstate` file this writes in `deploy/aws/bootstrap/`: you need it to change or remove the bootstrap.
5. **Set up your fork on GitHub:**
   - Settings, Environments: create `production`, and under deployment branches allow only `main`.
   - In `production`, add the environment secrets `OPENAI_API_KEY` (your key) and `BASIC_AUTH_HASH` (made as in B, step 2;
     paste it without quotes).
   - Settings, Secrets and variables, Actions, **Variables**: add `AWS_ROLE_ARN`, `TF_STATE_BUCKET` and `AWS_REGION` with the
     values step 4 printed, and optionally `BASIC_AUTH_USER` (default `team`).
6. **Deploy:** push to `main`, or Actions, CI/CD, Run workflow. The first run takes about 10 to 15 minutes. Your address
   (`https://<ip>.sslip.io`) appears in the run summary.
7. **When you are done:** Actions, **Destroy infrastructure**, type `destroy`. The server is billed by the hour while it exists.

Full details and troubleshooting: [cicd.md](cicd.md).

## Common problems

| Symptom | Fix |
|---|---|
| `docker compose up` stops with "set BASIC_AUTH_HASH in .env" | Add `BASIC_AUTH_USER` and `BASIC_AUTH_HASH` to `.env` (B, step 3). |
| The browser keeps asking for the password | Wrong password, or the hash in `.env` is missing its single quotes. |
| Answers fail with a "couldn't complete" message | The OpenAI key is missing or wrong, or its spend limit is reached: `docker compose logs api`. |
| "Could not assume role with OIDC" in your fork | `github_subject_prefix` or `github_repo` in C, step 4 does not match your fork exactly. Re-run that step with the right values. |
| CI fails at "no secrets in the code" | A key was committed. Rotate that key first, then remove it from the code; deleting it from git alone does not make it safe. |
