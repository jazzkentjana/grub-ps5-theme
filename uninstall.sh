#!/usr/bin/env bash
# grub-ps5-theme uninstaller: restores the GRUB settings that were saved before the first install.
#   sudo ./uninstall.sh
set -euo pipefail

THEME_DIR=/boot/grub/themes/ps5
STATE_DIR=/var/lib/grub-ps5-theme

[ "$(id -u)" -eq 0 ] || { echo "ERROR: run as root:  sudo ./uninstall.sh" >&2; exit 1; }
[ -f "$STATE_DIR/default-grub.orig" ] || { echo "ERROR: no saved backup found in $STATE_DIR - was the theme installed with install.sh?" >&2; exit 1; }

rm -f /etc/grub.d/09_ps5_menu_order /etc/grub.d/29_ps5_efi_class /etc/grub.d/39_ps5_class_reset
if [ -f "$STATE_DIR/10_linux_was_executable" ]; then chmod +x /etc/grub.d/10_linux; fi
cp "$STATE_DIR/default-grub.orig" /etc/default/grub
rm -rf "$THEME_DIR"
if [ -d "$STATE_DIR/theme.orig" ]; then cp -r "$STATE_DIR/theme.orig" "$THEME_DIR"; fi
update-grub
rm -f "$STATE_DIR/installed"
echo "Removed. Your original GRUB settings are restored (backups stay in $STATE_DIR)."
