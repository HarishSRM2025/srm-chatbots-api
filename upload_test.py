import os
import requests

url = "http://127.0.0.1:8000/api/knowledge/"
token = os.environ.get("SRM_API_TOKEN")

if not token:
    raise SystemExit(
        "SRM_API_TOKEN is not set. Set it in this PowerShell session first."
    )

file_path = "test-admissions.txt"

with open(file_path, "rb") as uploaded_file:
    response = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}"},
        data={
            "agent": "2",
            "title": "Test Knowledge - Admissions Document",
            "source_type": "file",
        },
        files={
            "file": ("test-admissions.txt", uploaded_file, "text/plain")
        },
        timeout=60,
    )

print("HTTP Status:", response.status_code)
print("Response:")
print(response.text)
