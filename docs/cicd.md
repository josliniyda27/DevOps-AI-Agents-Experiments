# CI/CD: GitHub Actions to GHCR and EC2

Team members who want to release changes, run it locally, or deploy their own copy: start with [team-setup.md](team-setup.md).

`.github/workflows/ci-cd.yml` tests every push and pull request. A push to `main` (or a manual run on `main`) also builds
the two images, pushes them to GitHub Container Registry, creates or updates the EC2 server with Terraform, deploys the
release to it, and tags the commit.

```
push to main
  ├─ Test: API + knowledge base │ web UI │ Terraform           (also on development and on pull requests)
  ├─ Version: v<MAJOR>.<MINOR>.<BUILD>
  ├─ Build and push: ghcr.io/<owner>/<repo>-api, -web       ┐ in parallel
  ├─ Infrastructure: terraform apply deploy/aws (EC2 server) ┘
  ├─ Deploy to EC2: Systems Manager Run Command -> docker compose pull + up, then an HTTPS smoke test
  └─ Tag the release: git tag v<MAJOR>.<MINOR>.<BUILD>
```

## Versions

Every release is tagged `vMAJOR.MINOR.BUILD`, for example `v0.1.42`:

- **MAJOR.MINOR** come from the `VERSION` file at the repository root (it contains `0.1`). Edit it to bump the version:
  `0.2` for new features, `1.0` for a breaking change.
- **BUILD** is the workflow's run number. GitHub increases it by one on every run of the workflow, on any branch, so it never
  repeats and never goes back to 0 when MAJOR.MINOR change. Gaps are normal: runs on `development` and on pull requests use
  numbers too but produce no release.

Each image gets three tags: `v0.1.42`, `sha-<commit>` and `latest`. The commit gets the git tag `v0.1.42`.

## How the deployment works

- **AWS login without stored keys.** The pipeline signs in with GitHub's OIDC token and assumes one IAM role, which only
  accepts jobs from this repository's `production` environment and is only allowed what `deploy/aws` needs.
- **Terraform state** is kept in an S3 bucket (versioned, encrypted, with S3 locking), so every run sees the same server.
- **No SSH.** The server has no open port 22. The pipeline sends the release through AWS Systems Manager Run Command,
  and you get a shell with `aws ssm start-session --target <instance_id>`.
- **Secrets** (`OPENAI_API_KEY`, `BASIC_AUTH_HASH`) go from GitHub secrets into Parameter Store as encrypted values. The
  server reads them into `/opt/knowledge-assistant/.env` during the deploy; they never appear in the command or the logs.
  The images in GHCR stay private: the deploy job's own short-lived token is handed to the server for one pull and deleted.
- **HTTPS without a domain.** The server's address is used as `<ip-with-dashes>.sslip.io`, and Caddy gets a certificate for it.
  The site keeps its login.

## One-time setup

You need: an AWS account and credentials with admin rights on your own machine (only for step 1), Terraform 1.10 or later,
and admin rights on the GitHub repository.

**1. Create the AWS side (once, from your machine).**

```bash
cd deploy/aws/bootstrap
terraform init
terraform apply -var github_repo=josliniyda27/DevOps-AI-Agents-Experiments -var region=ap-south-1
```

If the repository uses GitHub's immutable OIDC subjects, also pass its prefix. Check with
`gh api repos/<owner>/<repo>/actions/oidc/customization/sub`: when the answer has `"use_immutable_subject": true`, add
`-var 'github_subject_prefix=<the sub_claim_prefix value>'` (this repository needs
`repo:josliniyda27@54833804/DevOps-AI-Agents-Experiments@1388736404`).
If the account already trusts GitHub Actions (IAM, Identity providers, `token.actions.githubusercontent.com`), add
`-var create_oidc_provider=false`. The command prints `AWS_ROLE_ARN`, `TF_STATE_BUCKET` and `AWS_REGION`.
Keep the `terraform.tfstate` file it writes in that folder (it is git-ignored): you need it to change or remove the bootstrap.

**2. Create the `production` environment.** GitHub repository, Settings, Environments, New environment, `production`.
Recommended: under "Deployment branches" allow only `main`, and add yourself under "Required reviewers" if every deploy
should wait for your approval.

**3. Add the variables.** Settings, Secrets and variables, Actions, **Variables** tab:

| Variable | Value |
|---|---|
| `AWS_ROLE_ARN` | from step 1 |
| `TF_STATE_BUCKET` | from step 1 |
| `AWS_REGION` | from step 1, for example `ap-south-1` |
| `BASIC_AUTH_USER` | optional, the login name (default `team`) |
| `INSTANCE_TYPE` | optional, default `t3.small` (2 GB RAM; smaller is not recommended) |

**4. Add the secrets** to the `production` environment (Settings, Environments, `production`, Environment secrets), so only
the deploy job can read them, never a pull request from a fork:

| Secret | Value |
|---|---|
| `OPENAI_API_KEY` | a **new** key with a monthly spend limit set at OpenAI |
| `BASIC_AUTH_HASH` | the login password's hash: `docker run --rm -it caddy caddy hash-password` |

Paste the hash as printed, without quotes.

**5. Run it.** Merge to `main`, or Actions, CI/CD, Run workflow on `main`. The first run takes longest: the server is created
and installs Docker before the first deploy (about 10 to 15 minutes in total). When it finishes, the run summary and
the `production` environment show the address: `https://<ip-with-dashes>.sslip.io`.

## Where credentials live

| Credential | Where | Used by |
|---|---|---|
| `OPENAI_API_KEY`, `BASIC_AUTH_HASH` | GitHub `production` environment secrets, copied to AWS Parameter Store (encrypted) on each deploy | the deploy job, then the server |
| AWS access | none stored: the pipeline gets short-lived credentials from GitHub OIDC | infrastructure and deploy jobs |
| GHCR access | none stored: the workflow's own `GITHUB_TOKEN`, which expires with the run | build and deploy jobs |
| Your personal AWS keys and GitHub token | only your local `.env` (git-ignored) | you, for the one-time bootstrap |

`.env` and other key files are git-ignored, and every push runs gitleaks over the whole history, so a committed secret
fails the build. If one is ever committed, rotate it first: removing it from git does not make it safe again.

## Everyday use

- **Release:** push or merge to `main`. Only changed layers are rebuilt (build cache), and Terraform changes nothing when
  the server already matches.
- **Change the knowledge base:** commit the JSON changes. The API image rebuilds its vector store, so the next release
  serves them.
- **Roll back:** open an earlier successful run in Actions and re-run its "Deploy to EC2" job. It deploys that run's image tag,
  which is still in GHCR (the server also keeps a week of old images).
- **Rotate a secret:** update it in GitHub, then run the workflow again.
- **See the server:** `aws ssm start-session --region <region> --target <instance_id>`, then
  `cd /opt/knowledge-assistant && sudo docker compose ps` or `sudo docker compose logs -f api`.

## Turning it off

The EC2 server is billed by the hour while it exists. Actions, **Destroy infrastructure**, Run workflow, type `destroy`.
This deletes the server, its address and its stored settings. The images, tags, state bucket and pipeline role remain,
and the next run on `main` creates a new server (with a new IP, so a new address).

To remove the AWS bootstrap as well, empty the state bucket and run `terraform destroy` in `deploy/aws/bootstrap` with the
same `-var` values as in step 1.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| "Could not assume role with OIDC" / "Not authorized to perform sts:AssumeRoleWithWebIdentity" | The role does not trust the job's identity. Most often the repository uses immutable OIDC subjects and `github_subject_prefix` was not set in step 1; otherwise `AWS_ROLE_ARN` is wrong, the job is not in the `production` environment, or `github_repo` does not match the repository name exactly. |
| `terraform init` fails with "AccessDenied" on S3 | `TF_STATE_BUCKET` or `AWS_REGION` does not match the bootstrap output. |
| "Repository secret ... is not set" | Add the secret in step 4. |
| "did not come online in Systems Manager" | First boot is slow, or the server has no internet access. Check the instance in the EC2 console (System log). |
| Deploy fails at "Pulling" with "denied" | The GHCR package is not linked to this repository. GitHub, your profile, Packages, the package, Package settings, give this repository access. |
| Smoke test fails but the deploy succeeded | Caddy could not get a certificate yet. Check the server's ports 80/443 (security group) and `docker compose logs web`. |
