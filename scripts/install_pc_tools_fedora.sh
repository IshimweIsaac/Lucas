#!/usr/bin/env bash
# Optional packages for full Lucas PC control on Fedora
set -e
echo "Installing PC control dependencies..."
sudo dnf install -y wmctrl brightnessctl playerctl upower wtype tesseract
echo "Add user to video group for brightness (log out/in after):"
echo "  sudo usermod -aG video \$USER"
echo "For open-window list on Wayland, also run:"
echo "  bash scripts/install_gnome_windows_fedora.sh"
echo "Done. Restart Lucas and try: pc_controller action=status"
