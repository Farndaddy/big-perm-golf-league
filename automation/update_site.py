#!/usr/bin/env python3
"""
Big Perm Golf League — Weekly Update Script
============================================
Drop this week's files into Scorecards/MM-DD-YY/:
  - 18 Birdies scorecard screenshot(s)  →  scores read automatically
  - GHIN screenshot (named GHIN.PNG)    →  handicaps read automatically

Then run:
  python automation/update_site.py

What it does:
  1. Reads GHIN screenshot → extracts each player's HC index + playing HC
  2. Reads 18 Birdies scorecard(s) → extracts gross scores (guests filtered out)
  3. Calculates net scores using the live GHIN playing handicaps
  4. Sends everything to Google Sheet via Apps Script
  5. Rebuilds index.html leaderboard + hole averages
  6. Rebuilds all 5 player profile pages
  7. Commits and pushes to GitHub — site is live in ~60 seconds
"""

import os, sys, json, re, base64, subprocess, requests
from pathlib import Path
import anthropic

# ── Load config ───────────────────────────────────────────────
SCRIPT_DIR  = Path(__file__).parent
SITE_DIR    = Path(__file__).parent.parent
CONFIG_FILE = SCRIPT_DIR / "config.json"

if not CONFIG_FILE.exists():
    print("❌ config.json not found. Copy config.example.json → config.json and fill it in.")
    sys.exit(1)

with open(CONFIG_FILE) as f:
    cfg = json.load(f)

ANTHROPIC_KEY    = cfg["anthropic_api_key"]
APPS_SCRIPT_URL  = cfg.get("apps_script_url", "")
FALLBACK_PLAYING = cfg["playing_handicaps"]   # used only if no GHIN image found
FALLBACK_INDEX   = cfg["handicap_indices"]    # used only if no GHIN image found
REPO_REMOTE      = cfg.get("repo_remote", "origin")
REPO_BRANCH      = cfg.get("repo_branch", "main")

PLAYERS  = ["Farnia", "Owens", "Felter", "Carter", "Lorenz"]
HOLE_HC  = [11,7,9,3,5,17,1,13,15,16,2,10,12,6,14,4,18,8]
HOLE_PAR = [4,4,4,4,4,3,5,4,3,4,3,4,4,4,4,5,3,4]


# ── Helpers ───────────────────────────────────────────────────
def encode_image(img_path):
    with open(img_path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode("utf-8")
    media = "image/png" if img_path.suffix.lower() == ".png" else "image/jpeg"
    return {"type": "image", "source": {"type": "base64", "media_type": media, "data": data}}


def call_claude(image_parts, prompt, max_tokens=1024):
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    content = image_parts + [{"type": "text", "text": prompt}]
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": content}]
    )
    raw = response.content[0].text.strip()
    raw = re.sub(r'^```(?:json)?\s*', '', raw)
    raw = re.sub(r'\s*```$', '', raw)
    return json.loads(raw)


# ── Step 1: Find scorecard folder & separate files ────────────
def find_latest_scorecard_folder():
    scorecards_dir = SITE_DIR / "Scorecards"
    folders = sorted(scorecards_dir.glob("??-??-??"))
    if not folders:
        print("❌ No scorecard folders found in Scorecards/")
        sys.exit(1)
    latest = folders[-1]

    all_images = (list(latest.glob("*.PNG")) + list(latest.glob("*.png")) +
                  list(latest.glob("*.JPG")) + list(latest.glob("*.jpg")))
    if not all_images:
        print(f"❌ No images found in {latest}")
        sys.exit(1)

    # Separate GHIN/handicap screenshot from 18 Birdies scorecards
    # Matches filenames containing: ghin, playing, handicap, hc (case-insensitive)
    GHIN_KEYWORDS = ['ghin', 'playing', 'handicap', ' hc']
    ghin_image     = next((f for f in all_images
                           if any(kw in f.stem.lower() for kw in GHIN_KEYWORDS)), None)
    scorecard_imgs = [f for f in all_images if f != ghin_image]

    print(f"📂 Folder: {latest.name}")
    print(f"   Scorecard images: {len(scorecard_imgs)}")
    print(f"   GHIN image: {'✅ ' + ghin_image.name if ghin_image else '⚠️  not found — using config.json fallback'}")

    return latest, scorecard_imgs, ghin_image


# ── Step 2: Read GHIN screenshot for live handicaps ───────────
def extract_handicaps_from_ghin(ghin_image):
    """
    Returns two dicts:
      playing_hc  = { "Farnia": 19, "Owens": 12, ... }   ← course handicap at Glenview
      hc_index    = { "Farnia": 17.1, "Owens": 10.2, ... } ← CDGA handicap index
    """
    print("🏌️  Reading GHIN screenshot for handicaps...")

    prompt = f"""This is a GHIN (Golf Handicap and Information Network) screenshot showing
player handicap information for Glenview Park Golf Club.

The league members are: {', '.join(PLAYERS)}

Extract each player's:
1. Handicap Index (the CDGA number, e.g. 17.1)
2. Playing Handicap at Glenview Park Golf Club (the course handicap, e.g. 19)
   — this may be labeled "Course Handicap", "Playing Handicap", or similar.

Return ONLY valid JSON in this exact format:
{{
  "Farnia": {{"index": 17.1, "playing": 19}},
  "Owens":  {{"index": 10.2, "playing": 12}},
  "Felter": {{"index": 16.4, "playing": 18}},
  "Carter": {{"index": 14.2, "playing": 16}},
  "Lorenz": {{"index": 14.0, "playing": 14}}
}}

Only include players you can see in the screenshot. Do not guess.
Do not include any text outside the JSON.
"""

    data = call_claude([encode_image(ghin_image)], prompt)

    playing_hc = {}
    hc_index   = {}
    for player, vals in data.items():
        if player in PLAYERS:
            playing_hc[player] = int(vals["playing"])
            hc_index[player]   = float(vals["index"])
            print(f"   {player:8s}  Index {hc_index[player]}  →  Playing HC {playing_hc[player]}")

    return playing_hc, hc_index


# ── Step 3: Read 18 Birdies scorecard images ──────────────────
def extract_scores_from_images(scorecard_imgs):
    print("🤖 Reading 18 Birdies scorecard...")

    image_parts   = [encode_image(img) for img in scorecard_imgs]
    league_roster = ', '.join(PLAYERS)

    prompt = f"""You are reading 18 Birdies digital golf scorecard screenshots for the Big Perm Golf League.

The league has exactly 5 members: {league_roster}

Sometimes guest players (non-members) join the round. IGNORE ALL GUEST PLAYERS COMPLETELY.
Only extract scores for players whose name matches one of the 5 league members above.

Extract the GROSS score for every hole (1-18) for each league member who played.

Return ONLY valid JSON in this exact format:
{{
  "date": "Mon DD",
  "scores": {{
    "Farnia": [h1, h2, h3, h4, h5, h6, h7, h8, h9, h10, h11, h12, h13, h14, h15, h16, h17, h18],
    "Felter": [h1, h2, ...]
  }}
}}

Rules:
- ONLY include the 5 league members ({league_roster}). Skip any other names entirely.
- Only include a league member if they actually played. Omit DNS members.
- Gross scores only — raw strokes, not net.
- If a hole score is missing/illegible, use the most reasonable number from context.
- Date format: "May 31" (month name + day).
- No text outside the JSON.
"""

    data = call_claude(image_parts, prompt, max_tokens=1024)

    # Hard filter — remove any guest that slipped through
    guests = [name for name in data["scores"] if name not in PLAYERS]
    for name in guests:
        print(f"   🚫 Removed non-league player: {name}")
        del data["scores"][name]

    print(f"✅ Scores: {', '.join(data['scores'].keys())}  |  Date: {data['date']}")
    return data


# ── Step 4: Calculate net scores ─────────────────────────────
def calc_net_holes(gross_holes, hc):
    strokes = [0] * 18
    for i in range(18):
        if HOLE_HC[i] <= min(hc, 18):
            strokes[i] += 1
    if hc > 18:
        for i in range(18):
            if HOLE_HC[i] <= (hc - 18):
                strokes[i] += 1
    return [gross_holes[i] - strokes[i] for i in range(18)]


def calc_all_nets(scores, playing_hc):
    result = {}
    for player, gross_holes in scores.items():
        hc       = playing_hc.get(player, FALLBACK_PLAYING.get(player, 14))
        net_holes = calc_net_holes(gross_holes, hc)
        result[player] = {
            "gross_holes": gross_holes,
            "net_holes":   net_holes,
            "gross_total": sum(gross_holes),
            "net_total":   sum(net_holes),
            "hc":          hc
        }
    return result


# ── Step 5: Send to Google Sheet ─────────────────────────────
def send_to_google_sheet(date, scores, playing_hc, hc_index):
    if not APPS_SCRIPT_URL or "YOUR_DEPLOYMENT_ID" in APPS_SCRIPT_URL:
        print("⚠️  Apps Script URL not set — skipping Google Sheets update.")
        return

    payload = {
        "date":       date,
        "scores":     scores,
        "playing_hc": playing_hc,   # course handicap → written to Weekly Scorecard col V
        "hc_index":   hc_index      # CDGA index → for reference / profile badges
    }
    print("📊 Updating Google Sheet...")
    try:
        # Google Apps Script redirects POST requests — we must follow the redirect
        # manually and re-POST, otherwise Python converts the redirect to a GET (no body).
        resp = requests.post(APPS_SCRIPT_URL, json=payload, timeout=30,
                             allow_redirects=False)

        # Follow redirect (301/302) with a fresh POST to the final URL
        if resp.status_code in (301, 302, 303, 307, 308):
            redirect_url = resp.headers.get("Location")
            if redirect_url:
                resp = requests.post(redirect_url, json=payload, timeout=30)

        result = resp.json()
        if result.get("success"):
            print(f"✅ Sheet updated: {result.get('message')}")
        else:
            print(f"⚠️  Apps Script error: {result.get('error')}")
    except Exception as e:
        print(f"⚠️  Could not reach Apps Script: {e}")


# ── Step 6: Compute season context from index.html ────────────
def compute_season_stats(calc):
    html = (SITE_DIR / "index.html").read_text()
    m    = re.search(r'const d2026=(\[.*?\]);', html, re.DOTALL)
    if not m:
        print("⚠️  Could not parse d2026 array")
        return {p: [] for p in PLAYERS}

    season = {p: [] for p in PLAYERS}
    for (d, v_str, att_str) in re.findall(
            r"\{d:'([^']+)',v:\[([^\]]+)\],\s*att:\[([^\]]+)\]", m.group(1)):
        vals = [x.strip() for x in v_str.split(',')]
        atts = [x.strip().strip("'") for x in att_str.split(',')]
        for i, player in enumerate(PLAYERS):
            if atts[i] == 'IN':
                try:
                    season[player].append(int(vals[i]))
                except:
                    pass

    for player in PLAYERS:
        if player in calc:
            season[player].append(calc[player]["net_total"])
    return season


# ── Step 7: Update index.html ─────────────────────────────────
def update_index_html(date, calc, season):
    path = SITE_DIR / "index.html"
    html = path.read_text()

    # Normalize date: "Jun 07" → "Jun 7" to match d2026 format
    date_norm = re.sub(r' 0(\d),', r' \1,', date + ',')[:-1]

    # 7a — update the existing date row in d2026 with actual scores
    net_vals = [str(calc[p]["net_total"]) if p in calc else "null" for p in PLAYERS]
    att_vals = ["'IN'" if p in calc else "'OUT'" for p in PLAYERS]
    new_row  = f"{{d:'{date_norm}',v:[{','.join(net_vals)}],att:[{','.join(att_vals)}]}}"
    html = re.sub(
        rf"\{{d:'{re.escape(date_norm)}',v:\[[^\]]*\],\s*att:\[[^\]]*\](?:,[^}}]*)?\}}",
        new_row, html
    )

    # 7b — leaderboard
    avgs = {p: round(sum(s)/len(s), 1) for p, s in season.items() if s}
    ranked = sorted([(p, avgs[p], len(season[p])) for p in PLAYERS if p in avgs],
                    key=lambda x: (x[1], -x[2]))
    rank_classes = ['r1','r2','r3','','']
    rows = []
    for idx, (player, avg, rds) in enumerate(ranked):
        rc    = rank_classes[idx] if idx < 5 else ''
        badge = ' <span class="pbadge">DEF. CHAMP</span>' if player == 'Farnia' else ''
        best  = min(season[player])
        last  = season[player][-1]
        rows.append(
            f'    <div class="lb-row {rc}">\n'
            f'      <div class="rank">{idx+1}</div>\n'
            f'      <div class="pname">{player}{badge}</div>\n'
            f'      <div class="stat {"gold" if idx==0 else ""}">{avg}</div>'
            f'<div class="stat">{rds}</div>'
            f'<div class="stat {"good" if best < 72 else ""}">{best}</div>'
            f'<div class="stat">{last}</div>\n'
            f'    </div>'
        )
    html = re.sub(
        r'<!-- LIVE_LEADERBOARD_START -->.*?<!-- LIVE_LEADERBOARD_END -->',
        ('<!-- LIVE_LEADERBOARD_START -->\n'
         '  <div class="lb">\n'
         '    <div class="lb-head"><div>Rank</div><div>Player</div><div>Avg</div>'
         '<div>Rounds</div><div>Best</div><div>Last</div></div>\n'
         + '\n'.join(rows) +
         '\n  </div>\n  <!-- LIVE_LEADERBOARD_END -->'),
        html, flags=re.DOTALL
    )

    # 7c — round count in subtitle
    total_rds = max((len(s) for s in season.values() if s), default=1)
    html = re.sub(r'Round \d+ of 20 · [A-Za-z]+ \d+, 2026',
                  f'Round {total_rds} of 20 · {date}, 2026', html)

    path.write_text(html)
    print(f"✅ index.html — leaderboard + round count updated")
    print("   ℹ️  Per-hole averages: update manually this season (need full hole history per round)")


# ── Step 8: Update player profile pages ───────────────────────
def update_profile_page(player, date, calc, season, hc_index):
    fname = {
        "Farnia": "farnia_profile.html", "Owens":  "owens_profile.html",
        "Felter": "felter_profile.html", "Carter": "carter_profile.html",
        "Lorenz": "lorenz_profile.html"
    }[player]
    path = SITE_DIR / fname
    if not path.exists():
        return
    html = path.read_text()

    # Add scorecard row
    if player in calc:
        c = calc[player]
        nets = c["net_holes"]
        eagles  = sum(1 for i,h in enumerate(nets) if h <= HOLE_PAR[i]-2)
        birdies = sum(1 for i,h in enumerate(nets) if h == HOLE_PAR[i]-1)
        pars    = sum(1 for i,h in enumerate(nets) if h == HOLE_PAR[i])
        bogeys  = sum(1 for i,h in enumerate(nets) if h == HOLE_PAR[i]+1)
        doubles = sum(1 for i,h in enumerate(nets) if h == HOLE_PAR[i]+2)
        triples = sum(1 for i,h in enumerate(nets) if h >= HOLE_PAR[i]+3)

        entry = (f"  {{d:'{date}',gross:{c['gross_total']},hc:{c['hc']},net:{c['net_total']},"
                 f"holes:[{','.join(map(str,c['gross_holes']))}],"
                 f"b:{birdies},p:{pars},bo:{bogeys},dbl:{doubles},t:{triples}")
        if eagles:
            entry += f",eagle:{eagles}"
        entry += "},"

        # Find 2026 array and append
        m = re.search(r'(2026:\[)(.*?)(\n  \],)', html, re.DOTALL)
        if m:
            existing = m.group(2).rstrip().rstrip(',')
            html = html[:m.start(2)] + existing + ',\n' + entry + '\n' + html[m.end(2):]

    # Update HC index badge if we have fresh GHIN data
    if player in hc_index:
        idx = hc_index[player]
        html = re.sub(r'HC \d+\.\d+', f'HC {idx}', html)

    # Update season avg + rounds
    nets_season = season.get(player, [])
    rds = len(nets_season)
    if rds:
        avg = round(sum(nets_season) / rds, 1)
        html = re.sub(r'In Progress · [\d.]+ avg net', f'In Progress · {avg} avg net', html)
        # Update the 2026 season avg s-card
        html = re.sub(
            r'(<div id="sy2026"[^>]*>.*?s-card-val[^>]*>)([\d.]+)(</div><div class="s-card-label">Season Avg)',
            rf'\g<1>{avg}\g<3>', html, flags=re.DOTALL
        )
        # Update rounds played s-card for 2026
        html = re.sub(
            r'(<div id="sy2026"[^>]*>.*?s-card-val[^>]*>)(\d+)(</div><div class="s-card-label">Rounds Played)',
            rf'\g<1>{rds}\g<3>', html, flags=re.DOTALL
        )

    # Update career rounds
    career = sum(
        len(re.findall(r"\{d:'[^']+',gross:", block))
        for yr_block in re.findall(r'\d{4}:\[(.*?)\](?=,\s*\d{4}:|\s*\})', html, re.DOTALL)
        for block in [yr_block]
    )
    if career:
        html = re.sub(r'(<div class="rec-val[^"]*">)\d+(</div><div class="rec-label">Rounds Played)',
                      rf'\g<1>{career}\g<2>', html)

    path.write_text(html)
    net_str = str(calc[player]["net_total"]) if player in calc else "DNS"
    avg_str = str(round(sum(nets_season)/rds, 1)) if rds else "—"
    print(f"   ✅ {player:8s}  net {net_str:>3}  rounds {rds}  avg {avg_str}")


# ── Step 9: Git push ─────────────────────────────────────────
def git_push(date, players_played):
    print("\n🚀 Pushing to GitHub...")
    os.chdir(SITE_DIR)
    cmds = [
        ["git", "add", "-A"],
        ["git", "commit", "-m", f"Week update {date}: {', '.join(players_played)}"],
        ["git", "push", REPO_REMOTE, REPO_BRANCH]
    ]
    for cmd in cmds:
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"⚠️  {' '.join(cmd)} failed:\n{r.stderr}")
            return
    print("✅ Live at: https://farndaddy.github.io/big-perm-golf-league/")


# ── Main ──────────────────────────────────────────────────────
def main():
    print("\n🏌️  Big Perm Golf League — Weekly Update")
    print("=" * 45)

    # Step 1 — find folder & files
    folder, scorecard_imgs, ghin_image = find_latest_scorecard_folder()

    # Step 2 — read GHIN handicaps (live) or fall back to config
    if ghin_image:
        playing_hc, hc_index = extract_handicaps_from_ghin(ghin_image)
        # Fill in any players not shown in the GHIN screenshot from config fallback
        for p in PLAYERS:
            if p not in playing_hc:
                playing_hc[p] = FALLBACK_PLAYING.get(p, 14)
                hc_index[p]   = FALLBACK_INDEX.get(p, 14.0)
    else:
        playing_hc = FALLBACK_PLAYING.copy()
        hc_index   = FALLBACK_INDEX.copy()

    # Step 3 — read scores
    score_data = extract_scores_from_images(scorecard_imgs)
    date   = score_data["date"]
    scores = score_data["scores"]

    # Step 4 — net calculation using live playing handicaps
    calc = calc_all_nets(scores, playing_hc)

    print(f"\n📋 Results for {date}:")
    for p in PLAYERS:
        if p in calc:
            c = calc[p]
            print(f"   {p:8s}  gross {c['gross_total']}  HC {c['hc']}  net {c['net_total']}")
        else:
            print(f"   {p:8s}  DNS")

    # Step 5 — Google Sheet
    send_to_google_sheet(date, scores, playing_hc, hc_index)

    # Step 6 — season context
    season = compute_season_stats(calc)

    # Step 7 — index.html
    print("\n📝 Updating site files...")
    update_index_html(date, calc, season)

    # Step 8 — profiles
    for player in PLAYERS:
        try:
            update_profile_page(player, date, calc, season, hc_index)
        except Exception as e:
            print(f"   ⚠️  {player} profile error: {e}")

    # Step 9 — push
    git_push(date, [p for p in PLAYERS if p in calc])
    print("\n✨ Done!")


if __name__ == "__main__":
    main()
