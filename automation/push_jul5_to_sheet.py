#!/usr/bin/env python3
"""
One-shot script: push Jul 5, 2026 scores to the Google Sheet.
Run from Terminal:  python3 automation/push_jul5_to_sheet.py
"""

import requests, json

APPS_SCRIPT_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbz9aq0nNXer8PBwMP3n6QX1umcjD_9HKHr_-qYgVy-ApxvDzzKoCowboCpP37iHdNlcC/exec"
)

payload = {
    "date": "Jul 5",
    "playing_hc": {"Farnia": 18, "Felter": 17, "Lorenz": 15},
    "hc_index":   {"Farnia": 16.2, "Felter": 15.9, "Lorenz": 13.0},
    "scores": {
        "Farnia": [5,4,5,6,4,4,7,4,4, 4,5,5,5,5,4,7,5,6],
        "Felter": [4,6,3,4,6,4,6,5,4, 4,5,5,6,5,4,6,4,6],
        "Lorenz": [4,7,6,5,6,5,6,4,5, 4,5,4,5,5,7,6,3,4]
    }
}

print("📊 Sending Jul 5, 2026 scores to Google Sheet...")
print(f"   Farnia: gross 89  HC 18  net 71")
print(f"   Felter: gross 87  HC 17  net 70")
print(f"   Lorenz: gross 91  HC 15  net 76")
print()

try:
    url = APPS_SCRIPT_URL
    # Follow redirects manually — always re-POST to each redirect
    for attempt in range(6):
        resp = requests.post(url, json=payload, timeout=30, allow_redirects=False)
        print(f"   [{attempt+1}] status {resp.status_code}  url: {url[:80]}")

        if resp.status_code in (301, 302, 303, 307, 308):
            redirect_url = resp.headers.get("Location")
            if not redirect_url:
                print("❌ Redirect with no Location header.")
                break
            url = redirect_url
            continue  # POST again to the new URL

        # Got a non-redirect response
        raw = resp.text.strip()
        print(f"   Response ({len(raw)} chars): {raw[:200]}")

        if not raw:
            print("❌ Empty response from Apps Script. The deployment may need re-publishing.")
            print("   Open the sheet → Extensions → Apps Script → Deploy → Manage deployments")
            print("   Then click the pencil ✏️ → Version: New version → Deploy")
            break

        try:
            result = resp.json()
            if result.get("success"):
                print(f"\n✅ Google Sheet updated!")
                print(f"   {result.get('message', '')}")
            else:
                print(f"\n❌ Apps Script error: {result.get('error')}")
        except json.JSONDecodeError:
            print(f"\n❌ Response is not JSON. Raw content above.")
        break

except requests.exceptions.ConnectionError:
    print("❌ No internet connection — make sure you're online.")
except requests.exceptions.Timeout:
    print("❌ Request timed out. Try again in a minute.")
except Exception as e:
    print(f"❌ Unexpected error: {e}")
