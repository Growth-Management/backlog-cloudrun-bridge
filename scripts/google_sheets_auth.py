from pathlib import Path
from typing import Sequence


def build_sheets_service(
    auth_mode: str,
    scopes: Sequence[str],
    service_account_file: str = "",
    oauth_client_secret_file: str = "",
    oauth_token_file: str = "google-oauth-token.json",
):
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    normalized_auth_mode = auth_mode.strip().lower()
    if normalized_auth_mode == "service_account":
        if not service_account_file:
            raise ValueError(
                "GOOGLE_APPLICATION_CREDENTIALS is required when "
                "GOOGLE_AUTH_MODE=service_account"
            )
        credentials = service_account.Credentials.from_service_account_file(
            service_account_file,
            scopes=list(scopes),
        )
        return build("sheets", "v4", credentials=credentials)

    if normalized_auth_mode == "user_oauth":
        if not oauth_client_secret_file:
            raise ValueError(
                "GOOGLE_OAUTH_CLIENT_SECRET_FILE is required when "
                "GOOGLE_AUTH_MODE=user_oauth"
            )
        credentials = load_user_oauth_credentials(
            client_secret_file=oauth_client_secret_file,
            token_file=oauth_token_file,
            scopes=scopes,
        )
        return build("sheets", "v4", credentials=credentials)

    raise ValueError(
        "GOOGLE_AUTH_MODE must be either service_account or user_oauth"
    )


def load_user_oauth_credentials(
    client_secret_file: str,
    token_file: str,
    scopes: Sequence[str],
):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    token_path = Path(token_file)
    credentials = None
    if token_path.exists():
        credentials = Credentials.from_authorized_user_file(
            str(token_path),
            list(scopes),
        )

    if credentials and credentials.valid:
        return credentials

    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
    else:
        flow = InstalledAppFlow.from_client_secrets_file(
            client_secret_file,
            list(scopes),
        )
        credentials = flow.run_local_server(port=0)

    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(credentials.to_json(), encoding="utf-8")
    return credentials
