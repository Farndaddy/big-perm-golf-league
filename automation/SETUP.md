# Big Perm Golf League — Automation Setup

This is a one-time setup. After this, every week is just:
1. Drop the 18 Birdies screenshot(s) into `Scorecards/MM-DD-YY/`
2. Run `python automation/update_site.py`
3. Done — the site is live.

---

## Part 1: Install Python Dependencies

Open Terminal and run:

```bash
pip3 install anthropic requests
```

---

## Part 2: Get an Anthropic API Key

1. Go to https://console.anthropic.com
2. Sign in (or create a free account)
3. Click **API Keys** in the left sidebar
4. Click **Create Key** — name it "Big Perm Golf"
5. Copy the key (starts with `sk-ant-...`)

---

## Part 3: Set Up the Google Apps Script

This script runs inside your Google Sheet and receives score data.

1. Open your **2026 Big Perm Tee Times** Google Sheet
2. Click **Extensions → Apps Script**
3. Delete everything in the editor
4. Open `automation/apps_script.gs` from this folder and paste the entire contents
5. Click **Save** (disk icon)
6. Click **Deploy → New Deployment**
7. Under "Select type" choose **Web App**
8. Set:
   - Description: `Big Perm Score Receiver`
   - Execute as: **Me**
   - Who has access: **Anyone** *(needed so the Python script can call it)*
9. Click **Deploy**
10. Click **Authorize access** and approve the permissions
11. Copy the **Web App URL** — it looks like:
    `https://script.google.com/macros/s/AKfycbx.../exec`

> **Note:** Every time you edit the Apps Script, you must create a **New Deployment** (not update an existing one) for changes to take effect.

---

## Part 4: Create Your Config File

1. In this folder, copy `config.example.json` to `config.json`:
   ```bash
   cp automation/config.example.json automation/config.json
   ```
2. Open `config.json` and fill in:
   - `anthropic_api_key` — the key from Part 2
   - `apps_script_url` — the URL from Part 3

3. Update `playing_handicaps` and `handicap_indices` whenever CDGA handicaps change.

---

## Part 5: Test It

Run the script with this season's latest scorecard:

```bash
cd "/path/to/Big Perm Golf League"
python automation/update_site.py
```

You should see it:
- Find the scorecard images ✅
- Read all scores with Claude ✅
- Update your Google Sheet ✅
- Update index.html and all profiles ✅
- Push to GitHub ✅

---

## Weekly Workflow (After Setup)

```
Sunday after golf:
  1. Export 18 Birdies scorecard as screenshot
  2. Drop image(s) into:  Scorecards/MM-DD-YY/
  3. Open Terminal, run:  python automation/update_site.py
  4. Wait ~60 seconds, check the site
```

That's it.

---

## Troubleshooting

**"anthropic module not found"**
→ Run: `pip3 install anthropic requests`

**"Apps Script error: permission denied"**
→ Re-deploy the Apps Script and make sure "Who has access" is set to "Anyone"

**"Could not find d2026 array"**
→ The Python script couldn't parse index.html. Check the site files haven't been manually reformatted.

**Scores look wrong**
→ The image may have been blurry or partially cut off. You can manually review the JSON output from Claude in the terminal and correct it in the HTML files as usual.

**Handicaps changed**
→ Update `playing_handicaps` and `handicap_indices` in `config.json` before running.

---

## What Gets Updated Automatically

| File | What changes |
|------|-------------|
| `index.html` | `d2026` scores array, leaderboard standings, round count |
| `farnia_profile.html` | New scorecard row, rounds count, season avg |
| `owens_profile.html` | Same |
| `felter_profile.html` | Same |
| `carter_profile.html` | Same |
| `lorenz_profile.html` | Same |
| Google Sheet | Leaderboard tab, Weekly Scorecard tab, Schedule Tracker |
| GitHub Pages | Pushed automatically — site goes live |

---

## What Still Needs Claude (Occasionally)

- **Per-hole averages** (net2026Holes / gross2026Holes) — requires all rounds' hole data. For now, update these manually or ask Claude.
- **Smack talk** — Claude writes this each week in Cowork mode. The automation adds the score data; the trash talk is still a human-plus-Claude creative process.
- **5-Hole Draft table** — updated manually for now.
- **Handicap changes** — update `config.json` manually when CDGA posts new indices.
