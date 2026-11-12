#!/usr/bin/env bash
# grub-ps5-theme installer (Ubuntu / Debian-based, GRUB 2).
#
#   sudo ./install.sh [--name NAME] [--wallpaper FILE] [--timeout SECONDS] [--no-reorder]
#
# It backs up your GRUB settings, builds the theme from the generator, installs it,
# rebuilds the menu and checks the result. If a check fails, it restores everything by itself.
# Undo later with: sudo ./uninstall.sh
set -euo pipefail

THEME_DIR=/boot/grub/themes/ps5
STATE_DIR=/var/lib/grub-ps5-theme
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAME="${SUDO_USER:-${USER:-}}"
WALLPAPER=""
TIMEOUT=""
REORDER=1

usage() { sed -n '2,8p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }
die() { echo "ERROR: $*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --name) NAME="${2:?--name needs a value}"; shift 2 ;;
    --wallpaper) WALLPAPER="${2:?--wallpaper needs a file}"; shift 2 ;;
    --timeout) TIMEOUT="${2:?--timeout needs a number}"; shift 2 ;;
    --no-reorder) REORDER=0; shift ;;
    -h|--help) usage 0 ;;
    *) echo "Unknown option: $1" >&2; usage 1 ;;
  esac
done

[ "$(id -u)" -eq 0 ] || die "run as root:  sudo ./install.sh"
command -v update-grub >/dev/null || die "update-grub not found (this installer is for Ubuntu/Debian-based systems)"
command -v grub-mkfont >/dev/null || die "grub-mkfont not found (install the 'grub-common' package)"
command -v grub-script-check >/dev/null || die "grub-script-check not found (install the 'grub-common' package)"
python3 -c 'import PIL' 2>/dev/null || die "Python Pillow is missing. Install it:  sudo apt install python3-pil"
[ -f "$HERE/generator/build_theme.py" ] || die "generator/build_theme.py not found next to install.sh"
[ -n "$NAME" ] || NAME="User"
[ -z "$TIMEOUT" ] || [[ "$TIMEOUT" =~ ^[0-9]+$ ]] || die "--timeout must be a whole number of seconds"
[ -z "$WALLPAPER" ] || [ -f "$WALLPAPER" ] || die "wallpaper file not found: $WALLPAPER"
[ -d /sys/firmware/efi ] || echo "NOTE: this system booted in legacy BIOS mode; the theme should still work, but it is only tested with UEFI."

# ---------- backup (only the first time, so the original state is never overwritten) ----------
mkdir -p "$STATE_DIR"
if [ ! -f "$STATE_DIR/installed" ]; then
  cp /etc/default/grub "$STATE_DIR/default-grub.orig"
  [ -f /boot/grub/grub.cfg ] && cp /boot/grub/grub.cfg "$STATE_DIR/grub.cfg.orig"
  if [ -d "$THEME_DIR" ]; then cp -r "$THEME_DIR" "$STATE_DIR/theme.orig"; fi
  if [ -x /etc/grub.d/10_linux ]; then echo 1 > "$STATE_DIR/10_linux_was_executable"; fi
fi
# a per-run snapshot to roll back to if THIS run fails
cp /etc/default/grub "$STATE_DIR/default-grub.run"
rm -rf "$STATE_DIR/theme.run"; [ -d "$THEME_DIR" ] && cp -r "$THEME_DIR" "$STATE_DIR/theme.run" || true

rollback() {
  echo "Rolling back this run..."
  rm -f /etc/grub.d/09_ps5_menu_order /etc/grub.d/29_ps5_efi_class /etc/grub.d/39_ps5_class_reset
  if [ -f "$STATE_DIR/10_linux_was_executable" ]; then chmod +x /etc/grub.d/10_linux; fi
  cp "$STATE_DIR/default-grub.run" /etc/default/grub
  rm -rf "$THEME_DIR"; [ -d "$STATE_DIR/theme.run" ] && cp -r "$STATE_DIR/theme.run" "$THEME_DIR" || true
  update-grub || true
  echo "Rolled back. Your previous GRUB setup is restored."
}

# ---------- build the theme ----------
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
GEN_ARGS=(--out "$TMP/ps5" --name "$NAME")
[ -z "$WALLPAPER" ] && WALLPAPER="$HERE/assets/wallpaper-default.jpg"
GEN_ARGS+=(--wallpaper "$WALLPAPER")
echo "Building the theme (welcome name: $NAME) ..."
python3 "$HERE/generator/build_theme.py" "${GEN_ARGS[@]}"
[ -f "$TMP/ps5/theme.txt" ] || die "the generator did not produce a theme.txt"

# ---------- install ----------
rm -rf "$THEME_DIR"; mkdir -p "$(dirname "$THEME_DIR")"
cp -r "$TMP/ps5" "$THEME_DIR"; chmod -R a+rX "$THEME_DIR"

if [ "$REORDER" = 1 ]; then
  install -m 0755 "$HERE/grub.d/09_ps5_menu_order" /etc/grub.d/09_ps5_menu_order
  install -m 0755 "$HERE/grub.d/29_ps5_efi_class" /etc/grub.d/29_ps5_efi_class
  install -m 0755 "$HERE/grub.d/39_ps5_class_reset" /etc/grub.d/39_ps5_class_reset
fi

set_var() { sed -i "/^$1=/d" /etc/default/grub; printf '%s=%s\n' "$1" "$2" >> /etc/default/grub; }
set_var GRUB_THEME "\"$THEME_DIR/theme.txt\""
set_var GRUB_GFXMODE "1920x1080,auto"
set_var GRUB_TIMEOUT_STYLE "menu"
set_var GRUB_DISABLE_OS_PROBER "false"     # needed so Windows and other systems are detected
[ -z "$TIMEOUT" ] || set_var GRUB_TIMEOUT "$TIMEOUT"

# ---------- rebuild and check ----------
OUT="$(update-grub 2>&1)" || { echo "$OUT"; rollback; die "update-grub failed"; }
echo "$OUT"
CFG=/boot/grub/grub.cfg
OK=1
echo "$OUT" | grep -q "Found theme: $THEME_DIR/theme.txt" || { echo "CHECK FAILED: GRUB did not find the theme"; OK=0; }
grub-script-check "$CFG" || { echo "CHECK FAILED: grub.cfg has a syntax error"; OK=0; }
if [ "$REORDER" = 1 ]; then
  n_adv="$(grep -c -- '--class advanced' "$CFG" || true)"
  [ "$n_adv" = 1 ] || { echo "CHECK FAILED: expected one 'Advanced options' entry with its class, found $n_adv"; OK=0; }
fi
[ "$OK" = 1 ] || { rollback; die "checks failed - nothing was changed"; }

date > "$STATE_DIR/installed"
echo
echo "Done. The PS5-style menu is installed."
echo "  * Restart to see it. Use the Up/Down arrow keys; Enter boots the highlighted entry."
echo "  * If something looks wrong, press F12 at power-on to pick your OS, then run: sudo ./uninstall.sh"
echo "  * Preview without rebooting (optional): pipx install grub2-theme-preview, then"
echo "      grub2-theme-preview --resolution 1920x1080 $THEME_DIR"
