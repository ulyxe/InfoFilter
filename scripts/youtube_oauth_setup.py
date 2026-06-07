"""One-time OAuth2 setup script for YouTube playlist write access.

Usage:
    python scripts/youtube_oauth_setup.py --client-id CID --client-secret CSECRET
    python scripts/youtube_oauth_setup.py --client-id CID --client-secret CSECRET --port 8085

Prints the refresh token to copy into the YOUTUBE_REFRESH_TOKEN GitHub Secret.

Prerequisites:
    pip install google-auth-oauthlib

    In Google Cloud Console, add http://localhost:<PORT> as an authorized redirect
    URI for your OAuth2 credentials (application type: Desktop app).
    Default port is 8085. If blocked, try --port 8888 or --port 9090 and update
    the redirect URI in Google Cloud Console to match.
"""

import argparse


def main() -> None:
    from google_auth_oauthlib.flow import InstalledAppFlow

    parser = argparse.ArgumentParser(description="YouTube OAuth2 setup — generates a refresh token")
    parser.add_argument("--client-id", required=True, help="OAuth2 client ID from Google Cloud Console")
    parser.add_argument("--client-secret", required=True, help="OAuth2 client secret")
    parser.add_argument("--port", type=int, default=8085,
                        help="Local port for OAuth2 redirect (default: 8085). "
                             "Must match the redirect URI registered in Google Cloud Console.")
    args = parser.parse_args()

    redirect_uri = f"http://localhost:{args.port}"
    client_config = {
        "installed": {
            "client_id": args.client_id,
            "client_secret": args.client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }
    }

    print(f"[INFO] Starting local OAuth2 server on {redirect_uri}")
    print(f"[INFO] Make sure '{redirect_uri}' is registered as a redirect URI in Google Cloud Console.\n")

    flow = InstalledAppFlow.from_client_config(
        client_config,
        scopes=["https://www.googleapis.com/auth/youtube"],
    )
    creds = flow.run_local_server(port=args.port)

    print("\n✅ Authorization successful!\n")
    print(f"YOUTUBE_REFRESH_TOKEN:\n{creds.refresh_token}\n")
    print("Copy this value into your GitHub Secret YOUTUBE_REFRESH_TOKEN.")


if __name__ == "__main__":
    main()
