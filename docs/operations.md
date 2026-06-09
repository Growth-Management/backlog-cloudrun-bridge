# Operations

This document captures the standard checks for CI, Cloud Run deployment, and
production operations for `backlog-cloudrun-bridge`.

## GitHub Actions

Pull requests run the `CI` workflow. The workflow installs
`requirements-dev.txt` and runs `pytest`.

The `Deploy to Cloud Run` workflow runs on pushes to `main` and can also be
started with `workflow_dispatch`. It builds a Docker image, pushes it to
Artifact Registry, deploys Cloud Run, and verifies `/health`.

The workflows use Node 24-compatible action versions:

- `actions/checkout@v6`
- `actions/setup-python@v6`
- `google-github-actions/auth@v3`
- `google-github-actions/setup-gcloud@v3`

If GitHub reports a JavaScript action runtime warning, check each action's
latest major version before changing workflow behavior. Keep `ubuntu-latest`
unless a runner compatibility issue is confirmed.

## Cloud Run Health Check

Use Cloud Shell for direct Cloud Run checks:

```bash
export GCP_PROJECT_ID="sysmgmt-cloudrun-bridge"
export GCP_REGION="asia-northeast1"
export CLOUD_RUN_SERVICE="backlog-cloudrun-bridge"

SERVICE_URL="$(gcloud run services describe "${CLOUD_RUN_SERVICE}" \
  --project "${GCP_PROJECT_ID}" \
  --region "${GCP_REGION}" \
  --format 'value(status.url)')"

curl --fail --show-error --silent "${SERVICE_URL}/health"
```

Expected response:

```json
{"status":"ok","service":"backlog-cloudrun-bridge"}
```

Business API routes require a Bearer token. Do not use production secrets in
shell history or logs.

## Cloud Run Revision Checks

List recent revisions:

```bash
gcloud run revisions list \
  --service "${CLOUD_RUN_SERVICE}" \
  --project "${GCP_PROJECT_ID}" \
  --region "${GCP_REGION}"
```

Describe the active service:

```bash
gcloud run services describe "${CLOUD_RUN_SERVICE}" \
  --project "${GCP_PROJECT_ID}" \
  --region "${GCP_REGION}"
```

Confirm:

- The latest ready revision matches the GitHub Actions deploy.
- `APP_ENV=production` is set.
- `API_AUTH_TOKEN` and `BACKLOG_API_KEY` are mounted from Secret Manager.
- The runtime service account is
  `backlog-cloudrun-runtime@sysmgmt-cloudrun-bridge.iam.gserviceaccount.com`.

## Secret Manager Checks

Confirm required secrets exist and have enabled versions:

```bash
gcloud secrets versions list api-auth-token \
  --project "${GCP_PROJECT_ID}"

gcloud secrets versions list backlog-api-key \
  --project "${GCP_PROJECT_ID}"
```

Rotate secrets by adding a new version, then redeploy Cloud Run:

```bash
printf '%s' '<new value>' | \
  gcloud secrets versions add api-auth-token --data-file=- \
    --project "${GCP_PROJECT_ID}"
```

## Artifact Registry Checks

List recent container images:

```bash
gcloud artifacts docker images list \
  "${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/backlog-cloudrun/backlog-cloudrun-bridge" \
  --project "${GCP_PROJECT_ID}" \
  --include-tags
```

The deployed image tag should match the GitHub commit SHA from the deploy run.

## Logs

Read recent Cloud Run logs:

```bash
gcloud logging read \
  'resource.type="cloud_run_revision" AND resource.labels.service_name="backlog-cloudrun-bridge"' \
  --project "${GCP_PROJECT_ID}" \
  --limit 50 \
  --format json
```

Application logs are JSON and include request metadata such as `request_id`,
method, path, status code, and duration. They must not include Bearer tokens,
Backlog API keys, or request bodies containing sensitive data.

## Rollback

If a deployment breaks production behavior, route traffic back to a known good
revision first, then investigate:

```bash
gcloud run services update-traffic "${CLOUD_RUN_SERVICE}" \
  --project "${GCP_PROJECT_ID}" \
  --region "${GCP_REGION}" \
  --to-revisions "<revision-name>=100"
```

After rollback, check `/health`, review GitHub Actions logs, and inspect Cloud
Run revision logs before opening a follow-up fix.
