#!/usr/bin/env bash
set -euo pipefail

export GCP_PROJECT_ID="${GCP_PROJECT_ID:-sysmgmt-cloudrun-bridge}"
export GCP_PROJECT_NUMBER="${GCP_PROJECT_NUMBER:-657902475140}"
export GCP_REGION="${GCP_REGION:-asia-northeast1}"
export CLOUD_RUN_SERVICE="${CLOUD_RUN_SERVICE:-backlog-cloudrun-bridge}"
export ARTIFACT_REGISTRY_REPOSITORY="${ARTIFACT_REGISTRY_REPOSITORY:-backlog-cloudrun}"
export GITHUB_OWNER="${GITHUB_OWNER:-Growth-Management}"
export GITHUB_REPO="${GITHUB_REPO:-backlog-cloudrun-bridge}"
export DEPLOY_SERVICE_ACCOUNT="${DEPLOY_SERVICE_ACCOUNT:-gha-run-deployer}"
export RUNTIME_SERVICE_ACCOUNT="${RUNTIME_SERVICE_ACCOUNT:-backlog-cloudrun-runtime}"
export WORKLOAD_IDENTITY_POOL="${WORKLOAD_IDENTITY_POOL:-github-actions}"
export WORKLOAD_IDENTITY_PROVIDER="${WORKLOAD_IDENTITY_PROVIDER:-github-actions-provider}"

gcloud config set project "${GCP_PROJECT_ID}"

gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  secretmanager.googleapis.com \
  cloudbuild.googleapis.com

gcloud artifacts repositories create "${ARTIFACT_REGISTRY_REPOSITORY}" \
  --repository-format=docker \
  --location="${GCP_REGION}" \
  --description="Backlog Cloud Run bridge container images" || true

gcloud iam service-accounts create "${DEPLOY_SERVICE_ACCOUNT}" \
  --display-name="GitHub Actions Cloud Run deployer" || true

gcloud iam service-accounts create "${RUNTIME_SERVICE_ACCOUNT}" \
  --display-name="Backlog Cloud Run runtime" || true

for role in \
  roles/run.admin \
  roles/artifactregistry.writer \
  roles/iam.serviceAccountUser
do
  gcloud projects add-iam-policy-binding "${GCP_PROJECT_ID}" \
    --member="serviceAccount:${DEPLOY_SERVICE_ACCOUNT}@${GCP_PROJECT_ID}.iam.gserviceaccount.com" \
    --role="${role}"
done

gcloud projects add-iam-policy-binding "${GCP_PROJECT_ID}" \
  --member="serviceAccount:${RUNTIME_SERVICE_ACCOUNT}@${GCP_PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

gcloud iam workload-identity-pools create "${WORKLOAD_IDENTITY_POOL}" \
  --project="${GCP_PROJECT_ID}" \
  --location="global" \
  --display-name="GitHub Actions" || true

gcloud iam workload-identity-pools providers create-oidc "${WORKLOAD_IDENTITY_PROVIDER}" \
  --project="${GCP_PROJECT_ID}" \
  --location="global" \
  --workload-identity-pool="${WORKLOAD_IDENTITY_POOL}" \
  --display-name="GitHub Actions provider" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
  --attribute-condition="attribute.repository == '${GITHUB_OWNER}/${GITHUB_REPO}'" || true

gcloud iam service-accounts add-iam-policy-binding \
  "${DEPLOY_SERVICE_ACCOUNT}@${GCP_PROJECT_ID}.iam.gserviceaccount.com" \
  --project="${GCP_PROJECT_ID}" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${GCP_PROJECT_NUMBER}/locations/global/workloadIdentityPools/${WORKLOAD_IDENTITY_POOL}/attribute.repository/${GITHUB_OWNER}/${GITHUB_REPO}"

cat <<EOF

Cloud Shell setup completed.

Set these GitHub Actions Variables:

GCP_PROJECT_ID=${GCP_PROJECT_ID}
GCP_REGION=${GCP_REGION}
CLOUD_RUN_SERVICE=${CLOUD_RUN_SERVICE}
ARTIFACT_REGISTRY_REPOSITORY=${ARTIFACT_REGISTRY_REPOSITORY}
GCP_DEPLOY_SERVICE_ACCOUNT=${DEPLOY_SERVICE_ACCOUNT}@${GCP_PROJECT_ID}.iam.gserviceaccount.com
CLOUD_RUN_RUNTIME_SERVICE_ACCOUNT=${RUNTIME_SERVICE_ACCOUNT}@${GCP_PROJECT_ID}.iam.gserviceaccount.com
GCP_WORKLOAD_IDENTITY_PROVIDER=projects/${GCP_PROJECT_NUMBER}/locations/global/workloadIdentityPools/${WORKLOAD_IDENTITY_POOL}/providers/${WORKLOAD_IDENTITY_PROVIDER}

Create or update these secrets manually in Secret Manager:
- api-auth-token
- backlog-api-key
EOF
