# Cloud Shell Setup

Cloud Run へ GitHub Actions からデプロイできるようにするため、以下は Cloud Shell で実行します。

## 1. 前提値

```bash
export GCP_PROJECT_ID="sysmgmt-cloudrun-bridge"
export GCP_PROJECT_NUMBER="657902475140"
export GCP_REGION="asia-northeast1"
export CLOUD_RUN_SERVICE="backlog-cloudrun-bridge"
export ARTIFACT_REGISTRY_REPOSITORY="backlog-cloudrun"
export GITHUB_OWNER="Growth-Management"
export GITHUB_REPO="backlog-cloudrun-bridge"
export DEPLOY_SERVICE_ACCOUNT="gha-run-deployer"
export RUNTIME_SERVICE_ACCOUNT="backlog-cloudrun-runtime"
export WORKLOAD_IDENTITY_POOL="github-actions"
export WORKLOAD_IDENTITY_PROVIDER="github-actions-provider"
```

## 2. プロジェクトを選択

```bash
gcloud config set project "${GCP_PROJECT_ID}"
```

## 3. 必要な API を有効化

```bash
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  secretmanager.googleapis.com \
  cloudbuild.googleapis.com
```

## 4. Artifact Registry を作成

```bash
gcloud artifacts repositories create "${ARTIFACT_REGISTRY_REPOSITORY}" \
  --repository-format=docker \
  --location="${GCP_REGION}" \
  --description="Backlog Cloud Run bridge container images"
```

すでに存在する場合はこのコマンドは失敗します。その場合は既存リポジトリを使います。

## 5. デプロイ用サービスアカウントを作成

```bash
gcloud iam service-accounts create "${DEPLOY_SERVICE_ACCOUNT}" \
  --display-name="GitHub Actions Cloud Run deployer"
```

Cloud Run 実行用サービスアカウントも作成します。

```bash
gcloud iam service-accounts create "${RUNTIME_SERVICE_ACCOUNT}" \
  --display-name="Backlog Cloud Run runtime"
```

## 6. サービスアカウントに必要最小限のロールを付与

```bash
gcloud projects add-iam-policy-binding "${GCP_PROJECT_ID}" \
  --member="serviceAccount:${DEPLOY_SERVICE_ACCOUNT}@${GCP_PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/run.admin"

gcloud projects add-iam-policy-binding "${GCP_PROJECT_ID}" \
  --member="serviceAccount:${DEPLOY_SERVICE_ACCOUNT}@${GCP_PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.writer"

gcloud projects add-iam-policy-binding "${GCP_PROJECT_ID}" \
  --member="serviceAccount:${DEPLOY_SERVICE_ACCOUNT}@${GCP_PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser"

gcloud projects add-iam-policy-binding "${GCP_PROJECT_ID}" \
  --member="serviceAccount:${RUNTIME_SERVICE_ACCOUNT}@${GCP_PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

## 7. Secret Manager に秘密情報を登録

実値は Cloud Shell 上で入力してください。秘密情報は GitHub やコードに保存しません。

```bash
printf '%s' '<Cloud Run API 呼び出し元認証トークン>' | \
  gcloud secrets create api-auth-token --data-file=-

printf '%s' '<Backlog API キー>' | \
  gcloud secrets create backlog-api-key --data-file=-
```

すでに Secret が存在する場合は、次のように新しいバージョンを追加します。

```bash
printf '%s' '<Cloud Run API 呼び出し元認証トークン>' | \
  gcloud secrets versions add api-auth-token --data-file=-

printf '%s' '<Backlog API キー>' | \
  gcloud secrets versions add backlog-api-key --data-file=-
```

## 8. Workload Identity Federation を作成

```bash
gcloud iam workload-identity-pools create "${WORKLOAD_IDENTITY_POOL}" \
  --project="${GCP_PROJECT_ID}" \
  --location="global" \
  --display-name="GitHub Actions"
```

```bash
gcloud iam workload-identity-pools providers create-oidc "${WORKLOAD_IDENTITY_PROVIDER}" \
  --project="${GCP_PROJECT_ID}" \
  --location="global" \
  --workload-identity-pool="${WORKLOAD_IDENTITY_POOL}" \
  --display-name="GitHub Actions provider" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
  --attribute-condition="attribute.repository == '${GITHUB_OWNER}/${GITHUB_REPO}'"
```

## 9. GitHub Actions からサービスアカウントを利用できるようにする

```bash
gcloud iam service-accounts add-iam-policy-binding \
  "${DEPLOY_SERVICE_ACCOUNT}@${GCP_PROJECT_ID}.iam.gserviceaccount.com" \
  --project="${GCP_PROJECT_ID}" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${GCP_PROJECT_NUMBER}/locations/global/workloadIdentityPools/${WORKLOAD_IDENTITY_POOL}/attribute.repository/${GITHUB_OWNER}/${GITHUB_REPO}"
```

## 10. GitHub Variables に設定する値

GitHub リポジトリの Actions Variables に以下を設定します。

```text
GCP_PROJECT_ID=sysmgmt-cloudrun-bridge
GCP_REGION=asia-northeast1
CLOUD_RUN_SERVICE=backlog-cloudrun-bridge
ARTIFACT_REGISTRY_REPOSITORY=backlog-cloudrun
GCP_DEPLOY_SERVICE_ACCOUNT=gha-run-deployer@sysmgmt-cloudrun-bridge.iam.gserviceaccount.com
CLOUD_RUN_RUNTIME_SERVICE_ACCOUNT=backlog-cloudrun-runtime@sysmgmt-cloudrun-bridge.iam.gserviceaccount.com
GCP_WORKLOAD_IDENTITY_PROVIDER=projects/657902475140/locations/global/workloadIdentityPools/github-actions/providers/github-actions-provider
```

## 11. 確認

`main` ブランチへ反映後、GitHub Actions の `Deploy to Cloud Run` が起動します。完了後、workflow の最後で `/health` へ疎通確認します。
