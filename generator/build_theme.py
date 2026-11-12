#!/usr/bin/env python3
"""Generate a PS5-style "Welcome back" GRUB2 theme (1920x1080).

GRUB's boot_menu can only draw a vertical list, so this theme uses the
"full-screen icon" trick: every menu entry's icon is a complete 1920x1080
screen in which that entry is shown as the selected circle. The menu's
item_height equals the screen height, so exactly one entry (one screen) is
visible at a time, and the menu is 110% wide so the text label is pushed off
the right edge. Pressing Up/Down swaps to the next full-screen image.

The output folder is a drop-in for /boot/grub/themes/<name>:
    theme.txt, terminal_box_*.png, *.pf2 fonts, icons/<class>.png

Requirements: python3, Pillow (python3-pil), grub-mkfont (grub-common),
fonts-lato and fonts-dejavu-core.
"""
import argparse
import getpass
import math
import os
import random
import shutil
import subprocess
import sys

try:
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
except ImportError:  # pragma: no cover
    sys.exit("error: Pillow is required (Ubuntu/Debian: sudo apt install python3-pil)")

W, H = 1920, 1080
SS = 4  # supersampling factor for anti-aliased circles and glyphs

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_WALLPAPER = os.path.join(HERE, "..", "assets", "wallpaper-default.jpg")
DEFAULT_ENTRIES = "advanced:Advanced options,ubuntu:Ubuntu,windows:Windows,efi:UEFI Firmware Settings"
SUBTITLE = "Please select OS to boot:"

# Extra icon names GRUB may look up for the default classes (it tries an
# entry's --class names in order and uses the first icons/<class>.png found).
ALIASES = {
    "ubuntu": ["gnu-linux", "gnu", "linux", "os", "unknown"],
    "windows": ["windows10", "windows11"],
    "efi": ["uefi"],
}

# Circle centre spacing per entry count (4 entries = the approved layout).
SPACING = {3: 420, 4: 380, 5: 330}

THEME_TXT = """\
# GRUB2 gfxmenu theme - "PS5 Welcome" (1920x1080)
# Full-screen-icon trick: every menu item's icon is a complete 1920x1080 screen
# in which that entry is the selected one. item_height = screen height, so only
# one item is visible; width 110% pushes the text label off the right edge.
title-text: ""
desktop-color: "#03050e"
terminal-font: "DejaVu Sans Mono Regular 16"
terminal-box: "terminal_box_*.png"
terminal-left: "10%"
terminal-top: "64%"
terminal-width: "80%"
terminal-height: "26%"
terminal-border: "14"

# Countdown: declared BEFORE the menu - GRUB draws the first-declared component on top.
+ label {
  id = "__timeout__"
  left = 0
  top = 930
  width = 100%
  align = "center"
  text = "Booting in %d seconds"
  color = "#9a9eac"
  font = "Lato Regular 22"
}

+ boot_menu {
  left = 0%
  top = 0%
  width = 110%
  height = 100%
  item_font = "DejaVu Sans Regular 12"
  selected_item_font = "DejaVu Sans Regular 12"
  item_color = "#03050e"
  selected_item_color = "#03050e"
  icon_width = 1920
  icon_height = 1080
  item_height = 1080
  item_padding = 0
  item_icon_space = 0
  item_spacing = 0
  scrollbar = false
}
"""

# (output file, font family, style, size) - names must match theme.txt
PF2_FONTS = [
    ("lato_regular_22.pf2", "Lato", "Regular", 22),
    ("dejavu_sans_12.pf2", "DejaVu Sans", "Book", 12),
    ("dejavu_sans_mono_16.pf2", "DejaVu Sans Mono", "Book", 16),
]
APT_HINT = "install the fonts with: sudo apt install fonts-lato fonts-dejavu-core"

FONT_FILES = {
    ("Lato", "Regular"): "/usr/share/fonts/truetype/lato/Lato-Regular.ttf",
    ("Lato", "Medium"): "/usr/share/fonts/truetype/lato/Lato-Medium.ttf",
    ("DejaVu Sans", "Book"): "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ("DejaVu Sans Mono", "Book"): "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
}


# --------------------------------------------------------------------------- fonts
def find_font(family, style):
    """Return a TTF path for family/style, via the usual Debian path or fc-match."""
    path = FONT_FILES.get((family, style))
    if path and os.path.isfile(path):
        return path
    try:
        out = subprocess.run(
            ["fc-match", "-f", "%{file}|%{family}|%{style}", "%s:style=%s" % (family, style)],
            capture_output=True, text=True, check=True).stdout
        f, fams, styles = (out.split("|") + ["", ""])[:3]
        if family in [x.strip() for x in fams.split(",")] and \
                style in [x.strip() for x in styles.split(",")] and os.path.isfile(f):
            return f
    except (OSError, subprocess.CalledProcessError):
        pass
    sys.exit("error: font '%s %s' not found; %s" % (family, style, APT_HINT))


_font_cache = {}


def font(style, size):
    key = (style, size)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(find_font("Lato", style), size)
    return _font_cache[key]


def build_pf2(out_dir):
    mkfont = shutil.which("grub-mkfont")
    if not mkfont:
        sys.exit("error: grub-mkfont not found (Ubuntu/Debian: sudo apt install grub-common)")
    for fname, family, style, size in PF2_FONTS:
        subprocess.run([mkfont, "-s", str(size), "-o", os.path.join(out_dir, fname),
                        find_font(family, style)], check=True)


# --------------------------------------------------------------------------- icons
def circle_badge(d, top, bot):
    s = d * SS
    grad = Image.new("RGBA", (s, s))
    gd = ImageDraw.Draw(grad)
    for y in range(s):
        t = y / s
        gd.line([(0, y), (s, y)], fill=tuple(int(top[i] * (1 - t) + bot[i] * t) for i in range(3)) + (255,))
    m = Image.new("L", (s, s))
    ImageDraw.Draw(m).ellipse((0, 0, s - 1, s - 1), fill=255)
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    im.paste(grad, (0, 0), m)
    return im


GREY_TOP, GREY_BOT = (110, 118, 132), (70, 76, 90)


def icon_ubuntu(d, label=""):
    im = circle_badge(d, (240, 110, 60), (200, 70, 30))
    s = d * SS
    dr = ImageDraw.Draw(im)
    c, R, w = s / 2, s * 0.25, int(s * 0.07)
    dr.ellipse((c - R, c - R, c + R, c + R), outline="white", width=w)
    for k in range(3):
        ang = math.radians(k * 120)
        x, y = c + R * 1.13 * math.cos(ang), c + R * 1.13 * math.sin(ang)
        r, gpad = s * 0.068, s * 0.035
        dr.ellipse((x - r - gpad, y - r - gpad, x + r + gpad, y + r + gpad), fill=(222, 92, 46))
        dr.ellipse((x - r, y - r, x + r, y + r), fill="white")
    return im.resize((d, d), Image.LANCZOS)


def icon_windows(d, label=""):
    im = circle_badge(d, (40, 150, 240), (0, 95, 200))
    s = d * SS
    dr = ImageDraw.Draw(im)
    c, q, g = s / 2, s * 0.15, s * 0.022
    for sx in (-1, 1):
        for sy in (-1, 1):
            x0 = c + (g if sx > 0 else -g - q)
            y0 = c + (g if sy > 0 else -g - q)
            dr.rectangle((x0, y0, x0 + q, y0 + q), fill="white")
    return im.resize((d, d), Image.LANCZOS)


def icon_gear(d, label=""):
    im = circle_badge(d, GREY_TOP, GREY_BOT)
    s = d * SS
    dr = ImageDraw.Draw(im)
    c = s / 2
    Ro, Ri, n = s * 0.25, s * 0.19, 8
    pts = []
    for i in range(n * 4):
        a = 2 * math.pi * i / (n * 4) - math.pi / (n * 4) * 0.5
        r = Ro if (i % 4) in (0, 1) else Ri
        pts.append((c + r * math.cos(a), c + r * math.sin(a)))
    dr.polygon(pts, fill="white")
    dr.ellipse((c - Ri, c - Ri, c + Ri, c + Ri), fill="white")
    h = s * 0.085
    dr.ellipse((c - h, c - h, c + h, c + h), fill=(90, 97, 111))
    return im.resize((d, d), Image.LANCZOS)


def icon_sliders(d, label=""):
    im = circle_badge(d, GREY_TOP, GREY_BOT)
    s = d * SS
    dr = ImageDraw.Draw(im)
    c, half = s / 2, s * 0.24
    lw, kr = max(1, int(s * 0.035)), s * 0.062
    for row, kx in ((-1, -0.35), (0, 0.4), (1, -0.05)):
        y = c + row * s * 0.15
        dr.rounded_rectangle((c - half, y - lw / 2, c + half, y + lw / 2), radius=lw / 2, fill="white")
        x = c + kx * half
        dr.ellipse((x - kr, y - kr, x + kr, y + kr), fill=(88, 95, 109), outline="white", width=int(s * 0.03))
    return im.resize((d, d), Image.LANCZOS)


def icon_letter(d, label=""):
    """Fallback for custom classes: grey badge with the label's first letter."""
    im = circle_badge(d, GREY_TOP, GREY_BOT)
    s = d * SS
    dr = ImageDraw.Draw(im)
    ch = (label.strip()[:1] or "?").upper()
    f = font("Medium", int(s * 0.42))
    bb = dr.textbbox((0, 0), ch, font=f)
    dr.text(((s - (bb[2] - bb[0])) / 2 - bb[0], (s - (bb[3] - bb[1])) / 2 - bb[1]), ch, font=f, fill="white")
    return im.resize((d, d), Image.LANCZOS)


ICONS = {
    "ubuntu": icon_ubuntu, "gnu-linux": icon_ubuntu, "linux": icon_ubuntu, "gnu": icon_ubuntu,
    "windows": icon_windows, "windows10": icon_windows, "windows11": icon_windows,
    "efi": icon_gear, "uefi": icon_gear,
    "advanced": icon_sliders, "settings": icon_sliders,
}


def ring(d, width, col):
    s = d * SS
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse((0, 0, s - 1, s - 1), outline=col + (255,), width=width * SS)
    return im.resize((d, d), Image.LANCZOS)


def power_icon(d, col=(200, 200, 205)):
    s = d * SS
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    w, m = int(s * 0.09), s * 0.12
    dr.arc((m, m, s - m, s - m), -60, 240, fill=col + (255,), width=w)
    dr.line((s / 2, s * 0.04, s / 2, s * 0.48), fill=col + (255,), width=w)
    r = w / 2
    for (x, y) in ((s / 2, s * 0.04 + r), (s / 2, s * 0.48)):
        dr.ellipse((x - r, y - r, x + r, y + r), fill=col + (255,))
    return im.resize((d, d), Image.LANCZOS)


def gamepad(w, col=(225, 226, 232)):
    h = int(w * 0.62)
    im = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    S, c, hole = SS, col + (255,), (0, 0, 0, 0)
    d.rounded_rectangle((w * 0.12 * S, h * 0.08 * S, w * 0.88 * S, h * 0.62 * S), radius=h * 0.28 * S, fill=c)
    for sx in (0.22, 0.78):
        d.ellipse(((sx - 0.17) * w * S, h * 0.28 * S, (sx + 0.17) * w * S, h * 0.98 * S), fill=c)
    cx, cy, a, b = w * 0.29 * S, h * 0.38 * S, w * 0.05 * S, w * 0.016 * S
    d.rectangle((cx - a, cy - b, cx + a, cy + b), fill=hole)
    d.rectangle((cx - b, cy - a, cx + b, cy + a), fill=hole)
    for (dx, dy) in ((0, -1), (0, 1), (-1, 0), (1, 0)):
        x, y, r = w * 0.71 * S + dx * w * 0.045 * S, h * 0.38 * S + dy * w * 0.045 * S, w * 0.022 * S
        d.ellipse((x - r, y - r, x + r, y + r), fill=hole)
    return im.resize((w, h), Image.LANCZOS)


def dim(im, f):
    r, g, b, a = im.split()
    rgb = ImageEnhance.Brightness(Image.merge("RGB", (r, g, b))).enhance(f)
    out = ImageEnhance.Color(rgb).enhance(0.75).convert("RGBA")
    out.putalpha(a)
    return out


# --------------------------------------------------------------------------- background
def load_wallpaper(path):
    im = Image.open(path).convert("RGB")
    w, h = im.size
    if w * 9 > h * 16:          # too wide: crop sides
        nw = h * 16 // 9
        im = im.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
    elif w * 9 < h * 16:        # too tall: crop top/bottom
        nh = w * 9 // 16
        im = im.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))
    if im.size != (W, H):
        im = im.resize((W, H), Image.LANCZOS)
    return im


def background(path, centers):
    x_lo, x_hi = centers[0], centers[-1]
    bg = load_wallpaper(path).filter(ImageFilter.GaussianBlur(2.2))
    bg = ImageEnhance.Color(bg).enhance(0.85)
    bg = ImageEnhance.Brightness(bg).enhance(0.58)
    bg = Image.blend(bg, Image.new("RGB", (W, H), (4, 9, 30)), 0.32)
    # darker top and bottom
    mask = Image.new("L", (W, H))
    md = ImageDraw.Draw(mask)
    for y in range(H):
        t = y / H
        md.line([(0, y), (W, y)], fill=int(150 * (1 - math.sin(math.pi * min(1, t * 1.08)) ** 0.7)))
    mask = mask.filter(ImageFilter.GaussianBlur(40))
    bg = Image.composite(Image.new("RGB", (W, H), (2, 4, 14)), bg, mask)
    # warm light spill from the top-left
    spill = Image.new("L", (W, H))
    ImageDraw.Draw(spill).ellipse((-500, -700, 900, 500), fill=60)
    spill = spill.filter(ImageFilter.GaussianBlur(220))
    bg = Image.composite(Image.new("RGB", (W, H), (120, 100, 80)), bg, spill)
    # soft dark band behind the circles
    band = Image.new("L", (W, H))
    ImageDraw.Draw(band).ellipse((x_lo - 210, 280, x_hi + 210, 860), fill=95)
    band = band.filter(ImageFilter.GaussianBlur(170))
    bg = Image.composite(Image.new("RGB", (W, H), (2, 4, 14)), bg, band)
    # golden bokeh, kept out of the circle row
    rnd = random.Random(11)
    big = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    small = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    def clean(x, y):
        return 300 < y < 800 and x_lo - 170 < x < x_hi + 170

    def dot(layer, x, y, r, a, col):
        ImageDraw.Draw(layer).ellipse((x - r, y - r, x + r, y + r), fill=col + (a,))

    for _ in range(30):
        x = rnd.uniform(0, W)
        y = rnd.gauss(800 - (x - 960) * 0.2, 150)
        if clean(x, y):
            continue
        dot(big, x, y, rnd.uniform(8, 22), int(rnd.uniform(25, 60)),
            rnd.choice([(255, 196, 110), (255, 178, 90), (250, 215, 150)]))
    for _ in range(110):
        x = rnd.uniform(0, W)
        y = rnd.gauss(810 - (x - 960) * 0.22, 175)
        if clean(x, y):
            continue
        dot(small, x, y, rnd.uniform(1.5, 4.5), int(rnd.uniform(50, 130)),
            rnd.choice([(255, 205, 130), (255, 186, 100)]))
    bg = bg.convert("RGBA")
    bg.alpha_composite(big.filter(ImageFilter.GaussianBlur(4)))
    bg.alpha_composite(small.filter(ImageFilter.GaussianBlur(1.2)))
    return bg


# --------------------------------------------------------------------------- screens
def fit_font(dr, text, style, size, max_w, min_size=18):
    while size > min_size and dr.textlength(text, font=font(style, size)) > max_w:
        size -= 1
    return font(style, size)


def text_center(dr, y, s, f, fill):
    dr.text(((W - dr.textlength(s, font=f)) / 2, y), s, font=f, fill=fill)


def screen(bg, entries, centers, spacing, sel, title):
    img = bg.copy()
    over = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dr = ImageDraw.Draw(over)
    text_center(dr, 128, title, fit_font(dr, title, "Medium", 62, W - 160), (245, 246, 250, 255))
    text_center(dr, 216, SUBTITLE, font("Regular", 28), (165, 170, 184, 255))

    CY, SEL_D, UNS_D = 520, 210, 150
    white = (255, 255, 255)
    for i, (cls, label) in enumerate(entries):
        cx = centers[i]
        fn = ICONS.get(cls, icon_letter)
        if i == sel:
            halo = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            R = SEL_D // 2 + 40
            ImageDraw.Draw(halo).ellipse((cx - R, CY - R, cx + R, CY + R), fill=white + (40,))
            over.alpha_composite(halo.filter(ImageFilter.GaussianBlur(30)))
            RD = SEL_D + 40
            disc = Image.new("RGBA", (RD * SS, RD * SS), (0, 0, 0, 0))
            ImageDraw.Draw(disc).ellipse((0, 0, RD * SS - 1, RD * SS - 1), fill=(10, 12, 20, 150))
            over.alpha_composite(disc.resize((RD, RD), Image.LANCZOS), (cx - RD // 2, CY - RD // 2))
            over.alpha_composite(ring(RD, 4, white), (cx - RD // 2, CY - RD // 2))
            over.alpha_composite(fn(SEL_D, label), (cx - SEL_D // 2, CY - SEL_D // 2))
            over.alpha_composite(gamepad(44), (cx - 22, CY - RD // 2 - 48))
            f = fit_font(dr, label, "Medium", 32, spacing * 0.95)
            dr.text((cx - dr.textlength(label, font=f) / 2, CY + RD // 2 + 28), label, font=f,
                    fill=(255, 255, 255, 255))
        else:
            PD = UNS_D + 22
            plate = Image.new("RGBA", (PD * SS, PD * SS), (0, 0, 0, 0))
            ImageDraw.Draw(plate).ellipse((0, 0, PD * SS - 1, PD * SS - 1), fill=(255, 255, 255, 18))
            over.alpha_composite(plate.resize((PD, PD), Image.LANCZOS), (cx - PD // 2, CY - PD // 2))
            over.alpha_composite(dim(fn(UNS_D, label), 0.58), (cx - UNS_D // 2, CY - UNS_D // 2))
            f = fit_font(dr, label, "Regular", 26, spacing * 0.85)
            dr.text((cx - dr.textlength(label, font=f) / 2, CY + PD // 2 + 24), label, font=f,
                    fill=(150, 155, 168, 255))

    # power icon and key hints
    hf = font("Regular", 20)
    over.alpha_composite(power_icon(40), ((W - 40) // 2, 995))
    hx, hy = W - 250, 1010
    dr.rounded_rectangle((hx, hy, hx + 74, hy + 30), radius=15, outline=(200, 202, 210, 255), width=2)
    dr.text((hx + 13, hy + 3), "Enter", font=hf, fill=(220, 222, 228, 255))
    dr.text((hx + 88, hy + 3), "Select", font=hf, fill=(185, 188, 198, 255))
    hx = 70
    dr.rounded_rectangle((hx, hy, hx + 92, hy + 30), radius=15, outline=(200, 202, 210, 255), width=2)
    dr.text((hx + 14, hy + 3), "↑ / ↓", font=hf, fill=(220, 222, 228, 255))
    dr.text((hx + 106, hy + 3), "Switch", font=hf, fill=(185, 188, 198, 255))
    img.alpha_composite(over)
    return img.convert("RGB")


# --------------------------------------------------------------------------- console box
def terminal_box(out_dir):
    """9-slice glass box for the GRUB console (20 px tiles, 20.5 px corner radius)."""
    fill, edge, clear = (8, 12, 30, 190), (255, 255, 255, 70), (0, 0, 0, 0)
    r2 = 20.5 ** 2

    def inside(x, y):  # in a 40x40 rounded tile centred at (20, 20)
        return 0 <= x < 40 and 0 <= y < 40 and (x - 20) ** 2 + (y - 20) ** 2 <= r2

    nw = Image.new("RGBA", (20, 20))
    px = nw.load()
    for x in range(20):
        for y in range(20):
            if not inside(x, y):
                px[x, y] = clear
            elif x == 0 or y == 0 or not all(inside(x + dx, y + dy)
                                             for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                px[x, y] = edge
            else:
                px[x, y] = fill
    tiles = {
        "nw": nw,
        "ne": nw.transpose(Image.FLIP_LEFT_RIGHT),
        "sw": nw.transpose(Image.FLIP_TOP_BOTTOM),
        "se": nw.transpose(Image.ROTATE_180),
        "c": Image.new("RGBA", (20, 20), fill),
    }
    for name, box in (("n", (0, 0, 19, 0)), ("s", (0, 19, 19, 19)), ("w", (0, 0, 0, 19)), ("e", (19, 0, 19, 19))):
        t = Image.new("RGBA", (20, 20), fill)
        ImageDraw.Draw(t).rectangle(box, fill=edge)
        tiles[name] = t
    for name, t in tiles.items():
        t.save(os.path.join(out_dir, "terminal_box_%s.png" % name))


# --------------------------------------------------------------------------- main
def default_name():
    user = os.environ.get("SUDO_USER") or os.environ.get("USER") or getpass.getuser() or "there"
    return user.capitalize()


def parse_entries(spec):
    entries = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        cls, sep, label = part.partition(":")
        cls = cls.strip().lower()
        if not sep or not cls or not label.strip() or not all(c.isalnum() or c in "-_" for c in cls):
            sys.exit("error: bad entry '%s' (expected class:Label, class = letters, digits, - or _)" % part)
        entries.append((cls, label.strip()))
    if not 3 <= len(entries) <= 5:
        sys.exit("error: --entries needs 3 to 5 entries, got %d" % len(entries))
    if len({c for c, _ in entries}) != len(entries):
        sys.exit("error: --entries has a duplicate class")
    return entries


def main():
    ap = argparse.ArgumentParser(
        description="Build a PS5-style GRUB2 theme folder (1920x1080) for /boot/grub/themes/<name>.",
        epilog="Example: python3 build_theme.py --out ./ps5 --name Alex  "
               "then: sudo cp -r ./ps5 /boot/grub/themes/ and set GRUB_THEME in /etc/default/grub. "
               "The circle order must match the order of your GRUB menu entries.")
    ap.add_argument("--out", required=True, help="output theme folder (created if missing)")
    ap.add_argument("--wallpaper", default=DEFAULT_WALLPAPER,
                    help="background image, any size/aspect; center-cropped to 16:9 (default: assets/wallpaper-default.jpg)")
    ap.add_argument("--name", default=None,
                    help='name in the heading "Welcome <name>," (default: your login name, capitalized)')
    ap.add_argument("--entries", default=DEFAULT_ENTRIES,
                    help="comma-separated class:Label list, 3-5 items, left to right in GRUB menu order "
                         "(default: \"%s\")" % DEFAULT_ENTRIES.replace("%", "%%"))
    ap.add_argument("--preview-png", metavar="FILE", help="also save one screen here as a preview")
    ap.add_argument("--preview-class", metavar="CLASS",
                    help="which entry is selected in --preview-png (default: windows if present, else the first)")
    args = ap.parse_args()

    if not os.path.isfile(args.wallpaper):
        sys.exit("error: wallpaper not found: %s" % args.wallpaper)
    entries = parse_entries(args.entries)
    name = args.name if args.name is not None else default_name()
    title = "Welcome %s," % name.strip()

    n = len(entries)
    spacing = SPACING[n]
    centers = [int(W / 2 + (i - (n - 1) / 2) * spacing) for i in range(n)]

    out = args.out
    icons = os.path.join(out, "icons")
    os.makedirs(icons, exist_ok=True)

    build_pf2(out)  # fail early if fonts or grub-mkfont are missing
    with open(os.path.join(out, "theme.txt"), "w") as f:
        f.write(THEME_TXT)
    terminal_box(out)

    bg = background(args.wallpaper, centers)
    classes = [c for c, _ in entries]
    preview_cls = args.preview_class or ("windows" if "windows" in classes else classes[0])
    if preview_cls not in classes:
        sys.exit("error: --preview-class '%s' is not in --entries" % preview_cls)
    for i, (cls, _) in enumerate(entries):
        im = screen(bg, entries, centers, spacing, i, title)
        path = os.path.join(icons, cls + ".png")
        im.save(path, optimize=True)  # 24-bit RGB, non-interlaced: safe for GRUB
        for alias in ALIASES.get(cls, []):
            if alias not in classes:
                shutil.copyfile(path, os.path.join(icons, alias + ".png"))
        if args.preview_png and cls == preview_cls:
            d = os.path.dirname(os.path.abspath(args.preview_png))
            os.makedirs(d, exist_ok=True)
            shutil.copyfile(path, args.preview_png)
        print("wrote", path)
    print("theme ready in", os.path.abspath(out))


if __name__ == "__main__":
    main()
