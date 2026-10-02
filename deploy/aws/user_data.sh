#!/bin/bash
# Runs once when the server first starts: a swap file (safety net on a small machine), Docker with Compose, and the AWS CLI
# (the deploy script reads the app's settings from Parameter Store with it). The Systems Manager agent ships with
# Ubuntu's AWS images. The app itself is installed later by the pipeline (deploy/aws/remote-deploy.sh).
set -euxo pipefail

fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y docker.io docker-compose-v2 git
systemctl enable --now docker
usermod -aG docker ubuntu

snap install aws-cli --classic
mkdir -p /opt/knowledge-assistant
