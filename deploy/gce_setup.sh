#!/usr/bin/env bash
# Provision a GCE VM and deploy the Microstructure L2 ingestion daemon.

set -euo pipefail

PROJECT="${GCP_PROJECT:-$(gcloud config get-value project)}"
ZONE="${GCP_ZONE:-us-central1-a}"
VM_NAME="${GCP_VM_NAME:-microstructure-daemon}"
MACHINE_TYPE="${GCP_MACHINE_TYPE:-e2-small}"
DISK_SIZE="${GCP_DISK_SIZE:-20GB}"
REPO_DIR="/opt/microstructure"

echo "==> Provisioning VM: $VM_NAME in $PROJECT / $ZONE"

gcloud compute instances create "$VM_NAME" \
  --project="$PROJECT" \
  --zone="$ZONE" \
  --machine-type="$MACHINE_TYPE" \
  --boot-disk-size="$DISK_SIZE" \
  --boot-disk-type="pd-standard" \
  --image-family="debian-12" \
  --image-project="debian-cloud" \
  --tags="microstructure-daemon" \
  --metadata=startup-script='#!/bin/bash
    apt-get update -y
    apt-get install -y docker.io docker-compose-v2 git
    systemctl enable docker
    systemctl start docker
  '

echo "==> Waiting 30s for VM to boot..."
sleep 30

echo "==> Uploading source code..."
gcloud compute scp --recurse \
  --zone="$ZONE" \
  --project="$PROJECT" \
  . "${VM_NAME}:${REPO_DIR}" \
  --compress

if [[ -f .env ]]; then
  echo "==> Uploading .env..."
  gcloud compute scp \
    --zone="$ZONE" \
    --project="$PROJECT" \
    .env "${VM_NAME}:${REPO_DIR}/.env"
fi

echo "==> Installing systemd service..."
gcloud compute ssh "${VM_NAME}" --zone="$ZONE" --project="$PROJECT" --command="
  sudo cp ${REPO_DIR}/deploy/microstructure.service /etc/systemd/system/microstructure.service
  sudo systemctl daemon-reload
  sudo systemctl enable microstructure
  sudo systemctl start microstructure
  sudo systemctl status microstructure --no-pager
"

echo ""
echo "==> Done. Monitor with:"
echo "    gcloud compute ssh $VM_NAME --zone=$ZONE -- sudo journalctl -fu microstructure"
