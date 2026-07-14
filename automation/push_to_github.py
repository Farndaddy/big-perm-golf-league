#!/usr/bin/env python3
"""
push_to_github.py — Big Perm Golf League
Run this directly (no arguments) and it:
  1. Reads config.json for your GitHub PAT + Apps Script URL
  2. Reads round_data.json for this week's scores + commit message
  3. Pushes all site files to GitHub in one commit
  4. Posts the round data to Apps Script to update the Google Sheet

Usage: python3 push_to_github.py
  (no arguments needed — everything comes from config.json + round_data.json)
"""

import json, base64, os, sys, time
import urllib.request, urllib.error

# ── Paths ─────────────────────────────────────────────────────────────────────
HERE       = os.path.dirname(os.path.abspath(__file__))
CONFIG     = os.path.join(HERE, 'config.json')
ROUND_DATA = os.path.join(HERE, 'round_data.json')
SITE_ROOT  = os.path.normpath(os.path.join(HERE, '..'))

# Files to push every week (repo-relative paths)
WEEKLY_FILES = [
    'index.html',
    'owens_profile.html',
    'felter_profile.html',
    'carter_profile.html',
    'farnia_profile.html',
    'lorenz_profile.html',
    'automation/apps_script.gs',
]

API = 'https://api.github.com'


# ── GitHub helpers ────────────────────────────────────────────────────────────
def gh(method, path, token, repo=None, body=None):
    url     = f'{API}/repos/{repo}{path}' if repo else API + path
    headers = {
        'Authorization':        f'token {token}',
        'Accept':               'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'Content-Type':         'application/json',
        'User-Agent':           'BigPermGolfBot/1.0',
    }
    data = json.dumps(body).encode() if body else None
    req  = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        raise RuntimeError(f'GitHub {method} {path} → HTTP {e.code}: {err}')


def push_files(token, repo, branch, files, message):
    print(f'\n📤  Pushing {len(files)} file(s) to GitHub...')

    # 1 — current HEAD
    ref      = gh('GET', f'/git/refs/heads/{branch}', token, repo=repo)
    head_sha = ref['object']['sha']
    print(f'    HEAD: {head_sha[:7]}')

    # 2 — base tree
    commit        = gh('GET', f'/git/commits/{head_sha}', token, repo=repo)
    base_tree_sha = commit['tree']['sha']

    # 3 — create blobs
    tree_items = []
    for repo_path in files:
        local = os.path.join(SITE_ROOT, repo_path.replace('/', os.sep))
        if not os.path.exists(local):
            print(f'    ⚠  skip (not found): {repo_path}')
            continue
        with open(local, 'rb') as f:
            raw = f.read()
        blob = gh('POST', '/git/blobs', token, repo=repo,
                  body={'content': base64.b64encode(raw).decode(), 'encoding': 'base64'})
        tree_items.append({'path': repo_path, 'mode': '100644', 'type': 'blob', 'sha': blob['sha']})
        print(f'    ✓  {repo_path}  ({len(raw):,} bytes)')

    if not tree_items:
        print('    Nothing to push.')
        return

    # 4 — new tree
    tree = gh('POST', '/git/trees', token, repo=repo,
               body={'base_tree': base_tree_sha, 'tree': tree_items})

    # 5 — new commit
    commit = gh('POST', '/git/commits', token, repo=repo,
                 body={'message': message, 'tree': tree['sha'], 'parents': [head_sha]})

    # 6 — update branch ref
    gh('PATCH', f'/git/refs/heads/{branch}', token, repo=repo,
       body={'sha': commit['sha']})

    print(f'\n✅  GitHub push complete!')
    print(f'    Commit: {commit["sha"][:7]} — {message}')
    print(f'    View: https://farndaddy.github.io/big-perm-golf-league/')


# ── Apps Script (Google Sheet) ────────────────────────────────────────────────
def post_to_sheet(url, round_data):
    print(f'\n📊  Updating Google Sheet...')
    # Only send the fields Apps Script expects (not commit_message)
    payload = {k: v for k, v in round_data.items() if k != 'commit_message'}
    body    = json.dumps(payload).encode()
    req     = urllib.request.Request(url, data=body,
                headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            result = json.loads(r.read().decode())
            if result.get('success'):
                print(f'✅  Google Sheet updated: {result.get("message", "OK")}')
            else:
                print(f'⚠   Apps Script error: {result.get("error")}')
    except urllib.error.HTTPError as e:
        if 300 <= e.code < 400:
            print('✅  Google Sheet updated (redirect = normal for Apps Script)')
        else:
            print(f'⚠   Apps Script HTTP {e.code}: {e.read().decode()}')
    except Exception as e:
        print(f'⚠   Apps Script call failed: {e}')


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print('=' * 55)
    print('  Big Perm Golf League — Auto Publisher')
    print('=' * 55)

    # Load config
    if not os.path.exists(CONFIG):
        print(f'ERROR: config.json not found at {CONFIG}')
        sys.exit(1)
    with open(CONFIG) as f:
        cfg = json.load(f)

    token  = cfg.get('github_pat')
    repo   = cfg.get('github_repo', 'Farndaddy/big-perm-golf-league')
    branch = cfg.get('github_branch', 'main')
    as_url = cfg.get('apps_script_url')

    if not token:
        print('ERROR: github_pat missing from config.json')
        sys.exit(1)

    # Load round data
    if not os.path.exists(ROUND_DATA):
        print(f'ERROR: round_data.json not found at {ROUND_DATA}')
        print('       (Claude writes this file each week before you run this script)')
        sys.exit(1)
    with open(ROUND_DATA) as f:
        round_data = json.load(f)

    message = round_data.get('commit_message', 'Weekly update')
    print(f'\n  Round: {round_data.get("date", "??")}')
    print(f'  Commit message: {message}')

    # Push to GitHub
    push_files(token, repo, branch, WEEKLY_FILES, message)

    # Update Google Sheet
    if as_url and 'scores' in round_data:
        post_to_sheet(as_url, round_data)
    else:
        print('\n⚠   Skipping Google Sheet (no scores in round_data.json)')

    print('\n' + '=' * 55)
    print('  All done! Site is live.')
    print('=' * 55)


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f'\n❌  Error: {e}')
        sys.exit(1)
