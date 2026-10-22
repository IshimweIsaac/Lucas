#!/usr/bin/env bash
# Wayland window list/focus for Lucas on Fedora GNOME
set -euo pipefail

UUID="window-calls-extended@hseliger.eu"
EXT_DIR="${HOME}/.local/share/gnome-shell/extensions/${UUID}"
EXT_WEB="https://extensions.gnome.org/extension/4974/window-calls-extended/"

if ! command -v gnome-extensions >/dev/null 2>&1; then
  echo "Missing gnome-extensions. Install it:"
  echo "  sudo dnf install gnome-extensions-app"
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "Missing curl. Install it:"
  echo "  sudo dnf install curl"
  exit 1
fi

SHELL_MAJOR="$(gnome-shell --version 2>/dev/null | awk '{print $3}' | cut -d. -f1)"
if [[ -z "${SHELL_MAJOR}" ]]; then
  echo "Could not detect GNOME Shell version."
  exit 1
fi

TMP="$(mktemp -d)"
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

INFO_URL="https://extensions.gnome.org/extension-info/?uuid=${UUID}&shell_version=${SHELL_MAJOR}"
echo "Fetching extension metadata (GNOME Shell ${SHELL_MAJOR})..."
VERSION_TAG="$(curl -fsSL "$INFO_URL" | python3 -c "
import json, sys
data = json.load(sys.stdin)
print(data['version_tag'])
")"
ZIP_URL="https://extensions.gnome.org/download-extension/${UUID}.shell-extension.zip?version_tag=${VERSION_TAG}"
ZIP="${TMP}/window-calls-extended.zip"

echo "Downloading Window Calls Extended (version tag ${VERSION_TAG})..."
curl -fsSL -o "$ZIP" "$ZIP_URL"

echo "Installing extension bundle..."
# gnome-extensions install expects a .zip path, not the UUID string.
gnome-extensions install --force "$ZIP"

if [[ ! -d "${EXT_DIR}" ]]; then
  echo "Install failed — files not found under ${EXT_DIR}"
  echo "Try manually: ${EXT_WEB}"
  exit 1
fi

echo "Files installed: ${EXT_DIR}"

# Shell only picks up new extensions after login (or full GNOME restart).
if gnome-extensions enable "${UUID}" 2>/dev/null; then
  echo "Extension enabled in GNOME."
else
  echo "Enable will work after you log out and back in, then run:"
  echo "  gnome-extensions enable ${UUID}"
fi

echo ""
echo "Next steps:"
echo "  1. Log out and log back in (required once for new shell extensions)."
echo "  2. Restart Lucas (say “restart” or close and open the app)."
echo "  3. Ask: “What’s my PC status?” — you should see real window titles."
echo ""
echo "Until then, Lucas can still list running apps (Firefox, Chrome, …) without titles."
echo "Web page: ${EXT_WEB}"
