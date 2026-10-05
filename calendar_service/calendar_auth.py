from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]

flow = InstalledAppFlow.from_client_secrets_file("secrets/credentials.json", SCOPES)
creds = flow.run_local_server(port=8080,open_browser=False)

with open("secrets/token.json", "w") as f:
    f.write(creds.to_json())
print("token.json saved")