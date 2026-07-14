#!/bin/bash
# ============================================================
# Big Perm Golf League — One-Click Publisher
# Double-click this file to push the site to GitHub and
# update the Google Sheet. That's it. No Terminal needed.
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "============================================"
echo "  Big Perm Golf League — Publishing Site..."
echo "============================================"
echo ""

python3 "$SCRIPT_DIR/push_to_github.py"
EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
  echo "🏌️  Done! Check the site in a minute:"
  echo "   https://farndaddy.github.io/big-perm-golf-league/"
else
  echo "Something went wrong — show this window to Claude."
fi

echo ""
echo "Press any key to close..."
read -n 1 -s
