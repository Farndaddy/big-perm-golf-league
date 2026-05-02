#!/usr/bin/env python3
"""
Big Perm Golf League — Auto-Update Script
Fetches data from Google Sheets CSV → updates index.html

Run locally:
    cd "Big Perm Golf League"
    python3 scripts/update_site.py

Via GitHub Actions: triggered automatically every Sunday night (see .github/workflows/update-site.yml)

Requirements: Python 3.8+, no external dependencies (uses stdlib only)
"""

import csv
import io
import re
import sys
import urllib.request
import urllib.parse
from datetime import datetime

# ── CONFIG ────────────────────────────────────────────────────────────────────
SHEET_ID = "1qhktUjZc_yraZ4mxgN671vDmDSXILS5tTyM7vV56oVQ"
HTML_FILE = "index.html"

# Website player order — must match d2026 array in index.html
PLAYERS = ["Farnia", "Owens", "Felter", "Carter", "Lorenz"]

# Players who get a badge next to their name in the leaderboard
PLAYER_BADGES = {"Farnia": "DEF. CHAMP"}

# Total rounds in the 2026 season
TOTAL_ROUNDS = 20

# 5-Hole Draft: the 5 contested holes and their par values
FIVE_HOLE_HOLES  = [4, 8, 11, 13, 16]
FIVE_HOLE_PAR    = {4: 4, 8: 4, 11: 4, 13: 4, 16: 5}  # par 21 total

# ── FETCH ─────────────────────────────────────────────────────────────────────
def fetch_sheet_csv(sheet_name):
    """
    Fetch a single Google Sheets tab as CSV.
    The spreadsheet must be shared publicly ("Anyone with the link can view").
    Returns list-of-lists, or None on failure.
    """
    url = (
        f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"
        f"/gviz/tq?tqx=out:csv&sheet={urllib.parse.quote(sheet_name)}"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode("utf-8")
            return list(csv.reader(io.StringIO(text)))
    except Exception as e:
        print(f"  ERROR fetching '{sheet_name}': {e}", file=sys.stderr)
        return None


def _val(row, idx, default=None):
    """Safe column accessor with strip."""
    if idx >= len(row):
        return default
    v = str(row[idx]).strip()
    return v if v else default


def _num(row, idx):
    """Return float or None for a cell."""
    v = _val(row, idx)
    if v is None or v in ("#DIV/0!", "#N/A", "#VALUE!", "#REF!"):
        return None
    try:
        f = float(v)
        return f if f != 0 else None   # treat 0 as no data (sheet uses empty/0 for no-show)
    except ValueError:
        return None


def _parse_date(raw):
    """
    Parse a date string from Google Sheets CSV export.
    Google Sheets typically exports dates as M/D/YYYY (e.g. "4/26/2026").
    Returns a short label like "Apr 26".
    """
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            dt = datetime.strptime(raw.strip(), fmt)
            # %-d removes leading zero on Linux; use %#d on Windows if needed
            return dt.strftime("%b %-d")
        except ValueError:
            continue
    return raw.strip()  # fallback: return as-is


# ── PARSE LEADERBOARD TAB ─────────────────────────────────────────────────────
def parse_leaderboard(rows):
    """
    Parse the Leaderboard tab CSV.

    Sheet structure (0-indexed rows):
      Row 0  : header noise (col 7 = "8 Lowest Rounds for Avg", col 9+ = player names)
      Row 1  : "Date, Farnia, Felter, Owens, Carter, Lorenz, ..."
      Rows 2-21: 20 rounds of NET scores (one row per round)
      Row 22 : "Total, ..."
      Row 23 : "Top 8 Average, 73, 73, 77, 78, ..." ← official season avg
      ...
      Row 32 : "Top 8 5-Hole Draft Avg. Score"
      Row 33 : "Player/Hole, 4, 8, 11, 13, 16"
      Rows 34-38: per-player per-hole averages (Farn, Felter, Owens, Carter, Lorenz)
      Row 39 : "Par, 4, 4, 4, 4, 5"

    Leaderboard player column order: Farnia(1), Felter(2), Owens(3), Carter(4), Lorenz(5)
    """
    # ── Locate "Date" header row ──
    header_row = None
    for i, row in enumerate(rows):
        if _val(row, 0) == "Date":
            header_row = i
            break
    if header_row is None:
        print("  ERROR: 'Date' row not found in Leaderboard tab", file=sys.stderr)
        return None

    # Column order in Leaderboard CSV (indices 1–5)
    LB_PLAYERS = ["Farnia", "Felter", "Owens", "Carter", "Lorenz"]

    # ── Parse per-round NET scores ──
    rounds = []
    for i in range(header_row + 1, len(rows)):
        row = rows[i]
        date_raw = _val(row, 0)
        if not date_raw:
            continue
        if date_raw in ("Total", "Top 8 Average", "Top 10 Scores", "Top 9 Scores",
                        "Top 8 Scores", "Top 7 Scores", "Top 6 Scores", "Top 5 Scores"):
            break  # end of round data

        date_str = _parse_date(date_raw)
        scores = {p: _num(row, j + 1) for j, p in enumerate(LB_PLAYERS)}
        rounds.append({"date": date_str, "scores": scores})
        if len(rounds) >= TOTAL_ROUNDS:
            break

    # ── Parse Top 8 Average row ──
    top8_avg = {}
    for row in rows:
        if _val(row, 0) == "Top 8 Average":
            for j, p in enumerate(LB_PLAYERS):
                v = _val(row, j + 1)
                if v and v not in ("#DIV/0!", "#N/A"):
                    try:
                        top8_avg[p] = float(v)
                    except ValueError:
                        pass
            break

    # ── Parse 5-Hole Draft averages ──
    # Find the "Top 8 5-Hole Draft Avg. Score" section
    five_hole = {}
    in_draft = False
    hole_keys = []
    DRAFT_NAME_MAP = {
        "Farn": "Farnia", "Farnia": "Farnia",
        "Felter": "Felter", "Owens": "Owens",
        "Carter": "Carter", "Lorenz": "Lorenz",
    }
    for row in rows:
        first = _val(row, 0, "")
        if "5-Hole Draft" in first:
            in_draft = True
            continue
        if not in_draft:
            continue

        # Hole header row: first col "Player/Hole" or first data col is a hole number
        if first in ("Player/Hole",) or (_val(row, 1) in ("4", "4.0") and not hole_keys):
            hole_keys = []
            for j in range(1, 7):
                v = _val(row, j, "")
                if v:
                    # strip ".0" from "4.0"
                    hole_keys.append(v.rstrip("0").rstrip(".") or v)
            continue

        if first == "Par":
            in_draft = False
            continue

        player = DRAFT_NAME_MAP.get(first)
        if player and hole_keys:
            hdata = {}
            for j, hk in enumerate(hole_keys):
                hdata[hk] = _num(row, j + 1)
            # Total is the next column after the 5 holes
            total_raw = _val(row, len(hole_keys) + 1)
            try:
                hdata["total"] = float(total_raw) if total_raw else None
            except ValueError:
                hdata["total"] = None
            five_hole[player] = hdata

    return {
        "rounds": rounds,
        "top8_avg": top8_avg,
        "five_hole": five_hole,
    }


# ── PARSE SCHEDULE TRACKER TAB ────────────────────────────────────────────────
def parse_schedule(rows):
    """
    Parse the Schedule Tracker tab CSV.

    Sheet structure:
      Row 0  : "No. of Rnds, ..."
      Row 1  : "Handicap, Confirmed Players, 17.0, ..."
      Row 2  : "Date, , Farnia, Owens, Carter, Felter, Lorenz, Extras"
      Rows 3-22: 20 rounds (IN / OUT / TBD / blank)
      Row 23 : "Fee Paid, ..."  ← stop here

    Schedule column order: Farnia(2), Owens(3), Carter(4), Felter(5), Lorenz(6), Extras(7)
    """
    SCHED_PLAYERS  = ["Farnia", "Owens", "Carter", "Felter", "Lorenz"]
    SCHED_COLS     = [2, 3, 4, 5, 6]   # column indices in the CSV

    # Find header row with "Date"
    data_start = None
    for i, row in enumerate(rows):
        if _val(row, 0) == "Date":
            data_start = i + 1
            break
    if data_start is None:
        print("  ERROR: 'Date' header not found in Schedule Tracker", file=sys.stderr)
        return []

    schedule = []
    for i in range(data_start, len(rows)):
        row = rows[i]
        date_raw = _val(row, 0)
        if not date_raw or date_raw in ("Fee Paid", "Lorenz Paid", "Actual Paid",
                                         "Committed", "Due", "Collections"):
            break

        date_str = _parse_date(date_raw)
        extras = _val(row, 7, "")

        att = {}
        for p, col in zip(SCHED_PLAYERS, SCHED_COLS):
            v = _val(row, col, "")
            if not v:
                # Check Extras column for "PlayerName Avail"
                first_name = p.split()[0]
                if first_name in extras and "Avail" in extras:
                    v = "Avail"
                else:
                    v = "OUT"
            att[p] = v

        # Special-case: entire row is "No Round" (Mother's Day etc.)
        note = None
        if all(v == "OUT" for v in att.values()):
            # Check if extras indicates a skip week
            if "No Round" in extras or all(_val(row, c, "") == "OUT" for c in SCHED_COLS):
                note = "No Round"

        schedule.append({"date": date_str, "attendance": att, "note": note})

    return schedule


# ── BUILD JS d2026 ARRAY ──────────────────────────────────────────────────────
def build_d2026_js(lb_rounds, schedule):
    """
    Produce the JavaScript d2026 array string that replaces the existing one in index.html.
    Player order: [Farnia, Owens, Felter, Carter, Lorenz]
    """
    # Map lb_rounds (keyed by date string) for quick lookup
    lb_by_date = {r["date"]: r["scores"] for r in lb_rounds}

    lines = [
        "// d2026 player order: [Farnia, Owens, Felter, Carter, Lorenz]",
        "// att = attendance from Schedule Tracker: IN/OUT/TBD/Avail",
        "const d2026=[",
    ]

    for idx, sched in enumerate(schedule):
        date = sched["date"]
        att_map = sched["attendance"]
        note = sched.get("note")

        # NET scores from leaderboard (website order: Farnia, Owens, Felter, Carter, Lorenz)
        scores_lb = lb_by_date.get(date, {})
        v_arr = []
        for p in PLAYERS:
            s = scores_lb.get(p)
            v_arr.append(str(int(s)) if s is not None else "null")

        # Attendance (website order: Farnia, Owens, Felter, Carter, Lorenz)
        att_arr = [f"'{att_map.get(p, 'OUT')}'" for p in PLAYERS]

        scores_str = ",".join(v_arr)
        att_str    = ",".join(att_arr)
        comma      = "," if idx < len(schedule) - 1 else ""

        # Note must be INSIDE the object — don't close } before adding it
        entry = f"  {{d:'{date}',v:[{scores_str}], att:[{att_str}]"
        if note:
            entry += f", note:'{note}'"
        entry += "}"
        entry += comma
        lines.append(entry)

    lines.append("];")
    return "\n".join(lines)


# ── BUILD LEADERBOARD HTML ────────────────────────────────────────────────────
def build_leaderboard_html(top8_avg, lb_rounds):
    """
    Build the .lb div HTML for the live leaderboard section.
    Returns (rounds_played_count, html_string).
    """
    # Compute per-player stats
    standings = []
    for p in PLAYERS:
        played_scores = [
            r["scores"][p] for r in lb_rounds
            if r["scores"].get(p) is not None
        ]
        n = len(played_scores)
        avg = top8_avg.get(p)
        best = min(played_scores) if played_scores else None
        last = played_scores[-1] if played_scores else None
        standings.append({
            "player": p, "avg": avg, "rounds": n,
            "best": best, "last": last,
        })

    # Sort: players who've played (by avg asc), then no-shows
    played  = sorted([s for s in standings if s["rounds"] > 0],
                     key=lambda x: (x["avg"] or 999))
    no_show = [s for s in standings if s["rounds"] == 0]
    standings = played + no_show

    # Assign rank labels (handle ties)
    prev_avg, rank = None, 1
    for i, s in enumerate(standings):
        if s["rounds"] == 0:
            s["rank"] = "—"
            continue
        if s["avg"] == prev_avg and prev_avg is not None:
            s["rank"] = f"T{rank}"
            standings[i - 1]["rank"] = f"T{rank}"
        else:
            rank = i + 1
            s["rank"] = str(rank)
        prev_avg = s["avg"]

    rounds_played = max((s["rounds"] for s in standings), default=0)

    rows_html = []
    for s in standings:
        p = s["player"]
        badge_txt = PLAYER_BADGES.get(p, "")
        badge_html = f' <span class="pbadge">{badge_txt}</span>' if badge_txt else ""
        is_top = s["rank"] in ("1", "T1")
        row_cls = "lb-row r1" if is_top else "lb-row"

        if s["rounds"] == 0:
            rows_html.append(
                f'    <div class="{row_cls}"><div class="rank dim">—</div>'
                f'<div class="pname dim">{p}</div>'
                f'<div class="stat dim">—</div><div class="stat dim">0</div>'
                f'<div class="stat dim">—</div><div class="stat dim">—</div></div>'
            )
        else:
            avg_disp  = f"{s['avg']:.2f}".rstrip("0").rstrip(".") if s["avg"] else "—"
            avg_cls   = " gold" if is_top else ""
            best_disp = str(int(s["best"])) if s["best"] else "—"
            last_disp = str(int(s["last"])) if s["last"] else "—"
            rows_html.append(
                f'    <div class="{row_cls}">'
                f'<div class="rank">{s["rank"]}</div>'
                f'<div class="pname">{p}{badge_html}</div>'
                f'<div class="stat{avg_cls}">{avg_disp}</div>'
                f'<div class="stat">{s["rounds"]}</div>'
                f'<div class="stat good">{best_disp}</div>'
                f'<div class="stat">{last_disp}</div></div>'
            )

    full_html = (
        '  <div class="lb">\n'
        '    <div class="lb-head"><div>Rank</div><div>Player</div>'
        '<div>Avg</div><div>Rounds</div><div>Best</div><div>Last</div></div>\n'
        + "\n".join(rows_html)
        + "\n  </div>"
    )
    return rounds_played, full_html


# ── BUILD 5-HOLE DRAFT HTML ───────────────────────────────────────────────────
def build_five_hole_html(five_hole, rounds_played):
    """Build the 5-hole draft table HTML block (replaces just the table, not the outer div)."""
    HOLES     = FIVE_HOLE_HOLES
    HOLE_KEYS = [str(h) for h in HOLES]
    PAR_TOTAL = sum(FIVE_HOLE_PAR.values())  # 21

    label = "Season Avg" if rounds_played >= 2 else f"R{max(rounds_played,1)} Total"

    # Find best total for green highlight
    best_total = None
    for p in PLAYERS:
        d = five_hole.get(p, {})
        t = d.get("total")
        if t is not None and (best_total is None or t < best_total):
            best_total = t

    th_holes = "".join(f"<th>Hole {h}</th>" for h in HOLES)
    table_rows = []
    for p in PLAYERS:
        d = five_hole.get(p, {})
        has_data = any(d.get(k) is not None for k in HOLE_KEYS)

        if not has_data:
            cells = "".join('<td class="sc-dash">—</td>' for _ in HOLES)
            table_rows.append(
                f'        <tr><td style="font-weight:700;text-align:left">{p}</td>'
                f'{cells}<td class="sc-dash">DNS</td></tr>'
            )
        else:
            cells = ""
            for k in HOLE_KEYS:
                v = d.get(k)
                if v is None:
                    cells += '<td class="sc-dash">—</td>'
                else:
                    disp = int(v) if v == int(v) else round(v, 1)
                    cells += f"<td>{disp}</td>"
            total = d.get("total")
            if total is not None:
                is_best = (total == best_total)
                cls = ' class="sc-best"' if is_best else ""
                total_disp = int(total) if total == int(total) else round(total, 1)
                total_td = f"<td{cls}>{total_disp}</td>"
            else:
                total_td = '<td class="sc-dash">—</td>'
            table_rows.append(
                f'        <tr><td style="font-weight:700;text-align:left">{p}</td>'
                f'{cells}{total_td}</tr>'
            )

    par_cells = "".join(f"<td>{FIVE_HOLE_PAR[h]}</td>" for h in HOLES)
    table_rows.append(
        f'        <tr style="background:var(--card2)"><td>Par</td>'
        f'{par_cells}<td style="color:var(--gray)">{PAR_TOTAL}</td></tr>'
    )

    return (
        f'      <div class="tbl-label">2026 — 5-Hole Draft (Holes 4, 8, 11, 13, 16) '
        f'<span style="font-size:.75rem;font-family:sans-serif;color:var(--gray);letter-spacing:0">NET</span></div>\n'
        f'      <table><thead><tr><th>Player</th>{th_holes}<th>{label}</th></tr></thead>\n'
        f'      <tbody>\n'
        + "\n".join(table_rows)
        + "\n      </tbody>\n      </table>"
    )


# ── REPLACE BETWEEN MARKERS ───────────────────────────────────────────────────
def replace_between(html, start_marker, end_marker, new_content):
    """Replace everything between two markers (inclusive of markers) in an HTML string."""
    pattern = re.compile(
        re.escape(start_marker) + r".*?" + re.escape(end_marker),
        re.DOTALL,
    )
    replacement = f"{start_marker}\n{new_content}\n{end_marker}"
    result, count = pattern.subn(replacement, html)
    if count == 0:
        print(f"  WARNING: marker not found — {start_marker!r}", file=sys.stderr)
    return result


# ── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    print("🏌️  Big Perm Golf League — site update starting")

    # 1. Fetch CSVs from Google Sheets
    print("  → Fetching Leaderboard tab...")
    lb_rows = fetch_sheet_csv("Leaderboard")

    print("  → Fetching Schedule Tracker tab...")
    sched_rows = fetch_sheet_csv("Schedule Tracker")

    if lb_rows is None or sched_rows is None:
        print("FATAL: Could not fetch required sheet data. Aborting.", file=sys.stderr)
        sys.exit(1)

    # 2. Parse data
    lb_data  = parse_leaderboard(lb_rows)
    schedule = parse_schedule(sched_rows)

    if not lb_data:
        print("FATAL: Leaderboard parse failed.", file=sys.stderr)
        sys.exit(1)

    lb_rounds   = lb_data["rounds"]
    top8_avg    = lb_data["top8_avg"]
    five_hole   = lb_data["five_hole"]

    rounds_played = sum(
        1 for r in lb_rounds
        if any(v is not None for v in r["scores"].values())
    )
    print(f"  → {rounds_played} round(s) of data found")
    print(f"  → Players with averages: {list(top8_avg.keys())}")

    # 3. Build replacement content
    rounds_played_count, lb_html   = build_leaderboard_html(top8_avg, lb_rounds)
    d2026_js                        = build_d2026_js(lb_rounds, schedule)
    five_hole_html                  = build_five_hole_html(five_hole, rounds_played_count)

    last_round_date = lb_rounds[-1]["date"] if lb_rounds else "TBD"
    # Find actual last played date
    for r in reversed(lb_rounds):
        if any(v is not None for v in r["scores"].values()):
            last_round_date = r["date"]
            break

    # 4. Read index.html
    try:
        with open(HTML_FILE, "r", encoding="utf-8") as f:
            html = f.read()
    except FileNotFoundError:
        print(f"FATAL: {HTML_FILE} not found. Run from the project root.", file=sys.stderr)
        sys.exit(1)

    # 5. Apply updates

    # Live badge in header
    html = re.sub(
        r"2026 Season In Progress · Round \d+ Complete",
        f"2026 Season In Progress · Round {rounds_played_count} Complete",
        html,
    )

    # Season subtitle
    html = re.sub(
        r"Round \d+ of \d+ · [A-Za-z]+ \d+, 2026",
        f"Round {rounds_played_count} of {TOTAL_ROUNDS} · {last_round_date}, 2026",
        html,
    )

    # Leaderboard standings
    html = replace_between(html,
        "<!-- LIVE_LEADERBOARD_START -->",
        "<!-- LIVE_LEADERBOARD_END -->",
        lb_html,
    )

    # d2026 JS data array
    html = replace_between(html,
        "/* D2026_DATA_START */",
        "/* D2026_DATA_END */",
        d2026_js,
    )

    # 5-hole draft table
    html = replace_between(html,
        "<!-- FIVE_HOLE_2026_START -->",
        "<!-- FIVE_HOLE_2026_END -->",
        five_hole_html,
    )

    # 6. Write updated index.html
    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"  ✅ index.html updated — Round {rounds_played_count} of {TOTAL_ROUNDS}")
    print(f"  Last round played: {last_round_date}")
    print("  Done. Commit and push to deploy.")


if __name__ == "__main__":
    main()
