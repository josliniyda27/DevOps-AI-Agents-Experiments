#!/bin/bash
# Runs ON the EC2 server. The pipeline sends it through AWS Systems Manager Run Command together with compose.release.yml
# (saved as compose.yml next to it), and passes the release in the environment:
#   IMAGE_TAG, API_IMAGE, WEB_IMAGE, SITE_ADDRESS, BASIC_AUTH_USER, GHCR_USER, AWS_REGION
# Secrets never travel in the command: they are read here from Parameter Store (/knowledge-assistant/*).
set -euo pipefail

: "${IMAGE_TAG:?}" "${API_IMAGE:?}" "${WEB_IMAGE:?}" "${SITE_ADDRESS:?}" "${BASIC_AUTH_USER:?}" "${GHCR_USER:?}" "${AWS_REGION:?}"

APP_DIR=/opt/knowledge-assistant
PARAMS=/knowledge-assistant
export PATH="$PATH:/snap/bin"
cd "$APP_DIR"

# A brand-new server may still be installing Docker and the AWS CLI (user_data.sh).
cloud-init status --wait >/dev/null || true

param() {
  aws ssm get-parameter --region "$AWS_REGION" --name "$PARAMS/$1" --with-decryption --query Parameter.Value --output text
}

echo "Writing settings for $IMAGE_TAG"
umask 077
# Single quotes keep the password hash's "$" characters literal for Compose.
cat > .env.new <<EOF
API_IMAGE=$API_IMAGE
WEB_IMAGE=$WEB_IMAGE
IMAGE_TAG=$IMAGE_TAG
SITE_ADDRESS=$SITE_ADDRESS
BASIC_AUTH_USER=$BASIC_AUTH_USER
BASIC_AUTH_HASH='$(param basic-auth-hash)'
OPENAI_API_KEY='$(param openai-api-key)'
EMBEDDING_PROVIDER=local
EOF
mv .env.new .env

echo "Pulling $IMAGE_TAG"
param ghcr-token | docker login ghcr.io -u "$GHCR_USER" --password-stdin >/dev/null
trap 'docker logout ghcr.io >/dev/null 2>&1 || true' EXIT
docker compose pull --quiet
docker logout ghcr.io >/dev/null

echo "Starting $IMAGE_TAG"
docker compose up -d --remove-orphans --wait --wait-timeout 300

docker compose ps
docker image prune -af --filter "until=168h" >/dev/null    # keep a week of old releases for a quick rollback
echo "Deployed $IMAGE_TAG"
