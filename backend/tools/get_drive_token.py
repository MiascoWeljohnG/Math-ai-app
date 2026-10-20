"""One-time setup: sign in to Google as the account that should OWN the uploaded files, and create the
Drive folder the app will store them in.

Run this on your own computer (it opens a browser window):

    pip install google-auth-oauthlib google-api-python-client
    python tools/get_drive_token.py --client-secret-file client_secret.json

`client_secret.json` is the OAuth client you download from Google Cloud Console:
  APIs & Services -> Credentials -> Create credentials -> OAuth client ID -> Application type: Desktop app
  -> Download JSON.  (Also enable "Google Drive API" under APIs & Services -> Library.)

It prints four values. Put them in backend/.env for local use, and in Render -> Environment for production.
Treat them like passwords: anyone who has them can read and write the app's files in your Drive.
"""
import argparse
import sys

SCOPES = ["https://www.googleapis.com/auth/drive.file"]   # only files/folders this app creates


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--client-secret-file", default="client_secret.json")
    parser.add_argument("--folder-name", default="Isipnayan uploads", help="name of the Drive folder to create")
    args = parser.parse_args()

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        print("Missing libraries. Run: pip install google-auth-oauthlib google-api-python-client")
        return 1

    flow = InstalledAppFlow.from_client_secrets_file(args.client_secret_file, SCOPES)
    # offline + consent forces Google to hand out a refresh token even if you've approved this app before
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    if not creds.refresh_token:
        print("Google didn't return a refresh token. Remove the app at https://myaccount.google.com/permissions and run again.")
        return 1

    drive = build("drive", "v3", credentials=creds, cache_discovery=False)
    folder = drive.files().create(
        body={"name": args.folder_name, "mimeType": "application/vnd.google-apps.folder"}, fields="id,name",
    ).execute()

    print("\nSigned in. Created the Drive folder", repr(folder["name"]), "in your My Drive.\n")
    print("Add these to backend/.env and to Render -> Environment:\n")
    print(f"GOOGLE_CLIENT_ID={creds.client_id}")
    print(f"GOOGLE_CLIENT_SECRET={creds.client_secret}")
    print(f"GOOGLE_REFRESH_TOKEN={creds.refresh_token}")
    print(f"DRIVE_FOLDER_ID={folder['id']}")
    print("\nThen check them with:  python tools/check_drive.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
