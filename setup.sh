#!/bin/bash
# Solstice setup — auto-detects your PANW Google Drive account and writes .env
# Run once before `docker compose up -d`

set -e

CLOUDSTORE="$HOME/Library/CloudStorage"

# Find PANW Google Drive mount
GDRIVE_DIR=$(ls -d "$CLOUDSTORE"/GoogleDrive-*@paloaltonetworks.com 2>/dev/null | head -1)

if [ -z "$GDRIVE_DIR" ]; then
  echo "❌ No PANW Google Drive found in $CLOUDSTORE"
  echo "   Make sure Google Drive for Desktop is installed, signed in with your"
  echo "   @paloaltonetworks.com account, and set to Mirror Files mode."
  exit 1
fi

GDRIVE_ACCOUNT=$(basename "$GDRIVE_DIR" | sed 's/GoogleDrive-//')
echo "✅ Found Google Drive account: $GDRIVE_ACCOUNT"

# Write .env
cat > .env <<EOF
GDRIVE_ACCOUNT=$GDRIVE_ACCOUNT
EOF
echo "✅ Written .env"

# Verify required .gsheet files are accessible
MY_DRIVE="$GDRIVE_DIR/My Drive"
MISSING=0

check_gsheet() {
  local path="$1"
  local label="$2"
  if [ -f "$path" ]; then
    echo "✅ Found: $label"
  else
    echo "⚠️  Missing: $label"
    echo "   Expected at: $path"
    MISSING=$((MISSING + 1))
  fi
}

check_gsheet "$MY_DRIVE/EMEA CC /DC CSE Tracker (Instant sync underlying data to upgrade tracker).gsheet" "DC CSE Tracker"
check_gsheet "$MY_DRIVE/Cortex Cloud Work/Cortex Cloud Open XSUPs with TAC.gsheet" "XSUP Tracker"
check_gsheet "$MY_DRIVE/Cortex Cloud Work/Central Technical COE Tracker.gsheet" "COE Tracker"

if [ $MISSING -gt 0 ]; then
  echo ""
  echo "⚠️  $MISSING file(s) not found. Make sure Google Drive is fully synced"
  echo "   (Mirror Files mode, not Stream). The files will be discovered at"
  echo "   runtime — Refresh Data may fail until sync is complete."
fi

echo ""
echo "🚀 Ready. Run: docker compose up -d"
