#!/usr/bin/env python3
"""vfx.py - VFX pack for talking-head reels (Hebrew + English).

Effects: strike, echo, spotlight, freeze-mark, pinned-comment.
Text effects sit BEHIND the speaker (person segmentation), like pro reels.

Usage:
  vfx.py words IN [--lang he]                       word timestamps (faster-whisper)
  vfx.py strike IN OUT --text BORING --swap FRESH --at 2.1 [--strike-at 2.8] [--swap-at 3.3]
  vfx.py echo IN OUT --text "IN-APP BROWSER" --at 5 [--dur 2.5]
  vfx.py spotlight IN OUT --text "AI SLOP" --at 13 [--dur 2.5] [--color #FF5A36]
  vfx.py freeze-mark IN OUT --at 9.5 [--hold 1.5] [--label "תסתכלו כאן"] [--x .5 --y .3 --r .12]
  vfx.py pinned-comment IN OUT --user designnerd --text "..." --at 17 [--dur 4]
  vfx.py plan IN OUT plan.json                      several effects in one render
Common: --y (text center, fraction of height), --seg fast|quality, --crf
"""
import argparse, glob, json, math, os, re, subprocess, sys, tarfile
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, features

CACHE = os.path.expanduser(os.environ.get("VFX_CACHE", "~/.cache/vfx"))
HEB = re.compile(r"[\u0590-\u05FF]")
RAQM = features.check("raqm")


# ---------------------------------------------------------------- assets
def npm_fetch(pkg, pattern):
    d = os.path.join(CACHE, re.sub(r"[@/]", "_", pkg))
    if not glob.glob(os.path.join(d, "package", pattern)):
        os.makedirs(d, exist_ok=True)
        subprocess.run(["npm", "pack", pkg, "--pack-destination", d], check=True, capture_output=True)
        with tarfile.open(sorted(glob.glob(os.path.join(d, "*.tgz")))[-1]) as t:
            try:
                t.extractall(d, filter="data")
            except TypeError:
                t.extractall(d)
    return sorted(glob.glob(os.path.join(d, "package", pattern)))


def heebo(weight):
    """Heebo with Hebrew+Latin glyphs merged into one TTF (cached)."""
    out = os.path.join(CACHE, f"heebo-{weight}-full.ttf")
    if not os.path.exists(out):
        from fontTools.merge import Merger
        h = npm_fetch("@fontsource/heebo", f"files/heebo-hebrew-{weight}-normal.woff")[0]
        l = npm_fetch("@fontsource/heebo", f"files/heebo-latin-{weight}-normal.woff")[0]
        f = Merger().merge([h, l]); f.flavor = None; f.save(out)
    return out


FALLBACK = ["/System/Library/Fonts/Supplemental/Arial Black.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/Library/Fonts/Arial Bold.ttf", "C:/Windows/Fonts/arialbd.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]


def font_file(text, role="display", weight=900):
    he = bool(HEB.search(text))
    env = os.environ.get("VFX_FONT_HE" if he else ("VFX_FONT_EN" if role == "display" else "VFX_FONT_UI"))
    if env:
        return env
    try:
        if role == "display" and not he:
            return npm_fetch("@fontsource/anton", "files/anton-latin-400-normal.woff")[0]
        return heebo(weight)
    except Exception as e:
        print("font fetch failed, using system font:", e, file=sys.stderr)
        return next(p for p in FALLBACK if os.path.exists(p))


def shape(text):
    """Return (text, draw kwargs) with correct RTL handling."""
    if not HEB.search(text):
        return text, {}
    text = re.sub(r"(@[\w.]+)", "\u2066\\1\u2069", text)   # keep @handles in one LTR piece
    if RAQM:
        return text, {"direction": "rtl"}
    try:
        from bidi import get_display
    except ImportError:
        from bidi.algorithm import get_display
    return get_display(text), {}


# ---------------------------------------------------------------- text
def text_block(text, font, fill, stroke=0, stroke_fill=None, align="center", lh_mul=0.95, tight=False):
    lines = text.split("\n")
    shaped = [shape(l) for l in lines]
    boxes = [font.getbbox(t, stroke_width=stroke, **k) for t, k in shaped]
    if tight:  # display titles: line height from ink, like big reel captions
        lh = int(max(b[3] - b[1] for b in boxes) * 1.12)
    else:
        asc, desc = font.getmetrics(); lh = int((asc + desc) * lh_mul)
    pad = int(lh * 0.35) + stroke
    w, h = max(b[2] - b[0] for b in boxes) + 2 * pad, lh * len(lines) + 2 * pad
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for i, ((t, k), b) in enumerate(zip(shaped, boxes)):
        x, a = {"center": (w / 2, "mm"), "right": (w - pad, "rm"), "left": (pad, "lm")}[align]
        cy = pad + i * lh + lh / 2
        if tight:  # center the ink, not the font metrics (bbox is relative to the ascender line)
            cy = cy - (b[1] + b[3]) / 2; a = a[0] + "a"
        d.text((x, cy), t, font=font, fill=fill, anchor=a, stroke_width=stroke, stroke_fill=stroke_fill, **k)
    img.pad, img.nlines = pad, len(lines)
    return img


def fit_title(text, W, H, maxw=0.86, maxh=0.105, upper=True):
    """Pick font size + line split so a big title fills the frame like a pro reel."""
    if not HEB.search(text) and upper:
        text = text.upper()
    ff = font_file(text); probe = ImageFont.truetype(ff, 200)
    def size_for(t):
        bb = [probe.getbbox(shape(l)[0], **shape(l)[1]) for l in t.split("\n")]
        wmax = max(b[2] - b[0] for b in bb); hmax = max(b[3] - b[1] for b in bb)
        return int(min(200 * maxw * W / wmax, 200 * maxh * H / hmax))
    cands = [text]; words = text.split()
    if "\n" not in text and len(words) > 1:
        best = min(range(1, len(words)), key=lambda i: abs(len(" ".join(words[:i])) - len(" ".join(words[i:]))))
        cands.append(" ".join(words[:best]) + "\n" + " ".join(words[best:]))
    t = max(cands, key=lambda c: size_for(c) * (0.82 if "\n" in c and "\n" not in text else 1))
    return t, ImageFont.truetype(ff, size_for(t))


# ---------------------------------------------------------------- helpers
def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def ease_out_cubic(p): p = clamp(p); return 1 - (1 - p) ** 3
def ease_out_back(p, s=1.7): p = clamp(p) - 1; return 1 + (s + 1) * p ** 3 + s * p ** 2
def prog(t, a, d): return clamp((t - a) / d) if d > 0 else float(t >= a)


def hex_rgb(h): h = h.lstrip("#"); return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def with_alpha(img, a):
    if a >= 0.999: return img
    img = img.copy(); img.putalpha(img.getchannel("A").point(lambda v: int(v * clamp(a)))); return img


def scaled(img, s):
    if abs(s - 1) < 1e-3: return img
    out = img.resize((max(1, int(img.width * s)), max(1, int(img.height * s))), Image.BICUBIC)
    for k in ("pad", "nlines"):
        if hasattr(img, k): setattr(out, k, getattr(img, k))
    return out


def paste_center(canvas, img, cx, cy):
    x, y = int(cx - img.width / 2), int(cy - img.height / 2)
    sx, sy = max(0, -x), max(0, -y)
    img = img.crop((sx, sy, min(img.width, canvas.width - x), min(img.height, canvas.height - y)))
    if img.width > 0 and img.height > 0:
        canvas.alpha_composite(img, (x + sx, y + sy))


# ---------------------------------------------------------------- segmentation
class Segmenter:
    def __init__(self, mode="auto"):
        self.kind = None
        if mode in ("auto", "quality"):
            try:
                from rembg import new_session, remove
                self.sess, self.remove, self.kind = new_session("u2net_human_seg"), remove, "rembg"
            except Exception as e:
                if mode == "quality": print("rembg unavailable, falling back:", e, file=sys.stderr)
        if self.kind is None:
            from ai_edge_litert.interpreter import Interpreter
            p = npm_fetch("@mediapipe/selfie_segmentation", "selfie_segmentation.tflite")[0]
            self.it = Interpreter(model_path=p); self.it.allocate_tensors()
            self.inp, self.out, self.kind = self.it.get_input_details()[0], self.it.get_output_details()[0], "selfie"
        self.prev = None

    def __call__(self, frame, smooth=True):
        H, W = frame.shape[:2]
        if self.kind == "rembg":
            m = np.asarray(self.remove(Image.fromarray(frame), session=self.sess, only_mask=True), np.float32) / 255
        else:
            x = np.asarray(Image.fromarray(frame).resize((256, 256), Image.BILINEAR), np.float32)[None] / 255
            self.it.set_tensor(self.inp["index"], x); self.it.invoke()
            m = self.it.get_tensor(self.out["index"])[0, :, :, 0]
            m = np.asarray(Image.fromarray((m * 255).astype(np.uint8)).resize((W, H), Image.BICUBIC), np.float32) / 255
            m = np.clip((m - 0.35) / 0.3, 0, 1)
        m = np.asarray(Image.fromarray((m * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(max(1, W // 400))), np.float32) / 255
        if smooth and self.prev is not None and self.prev.shape == m.shape:
            m = 0.55 * m + 0.45 * self.prev
        self.prev = m
        return m


def head_top(mask):
    H, W = mask.shape
    rows = np.where(mask[:, int(W * 0.2):int(W * 0.8)].max(1) > 0.5)[0]
    return int(rows[0]) if len(rows) else None


def face_box(frame):
    """Face rectangle via OpenCV (if installed): returns cx, cy, rx, ry of an ellipse hugging face+beard."""
    try:
        import cv2
    except ImportError:
        return None
    g = cv2.cvtColor(np.ascontiguousarray(frame), cv2.COLOR_RGB2GRAY)
    k = 720 / max(g.shape); small = cv2.equalizeHist(cv2.resize(g, None, fx=k, fy=k))
    det = cv2.CascadeClassifier(os.path.join(getattr(cv2, "data", None) and cv2.data.haarcascades or "", "haarcascade_frontalface_default.xml"))
    if det.empty():  # OpenCV 5 dropped bundled cascades: pip install "opencv-python-headless<5"
        return None
    found = det.detectMultiScale(small, 1.08, 6, minSize=(40, 40))
    if len(found) == 0:
        return None
    x, y, w, h = [v / k for v in max(found, key=lambda r: r[2] * r[3])]
    return x + w / 2, y + h * 0.58, w * 0.68, h * 0.8


def head_box(mask):
    """Approximate head center/radius from the person mask."""
    H, W = mask.shape
    rows = np.where(mask.max(1) > 0.5)[0]
    if len(rows) == 0: return W / 2, H * 0.3, W * 0.15
    top = rows[0]; band = mask[top:top + int(H * 0.16)] > 0.5
    xs = np.where(band.any(0))[0]
    cx = (xs[0] + xs[-1]) / 2 if len(xs) else W / 2
    r = max(W * 0.1, (xs[-1] - xs[0]) / 2 * 1.15 if len(xs) else W * 0.15)
    return cx, top + r * 0.95, r


# ---------------------------------------------------------------- effects
class Effect:
    needs_mask = False
    occlude = False          # True = drawn behind the speaker
    overlap = 0.3            # share of the last title line hidden behind the head
    def __init__(self, W, H, **o): self.W, self.H, self.o = W, H, o
    def setup(self, mask): pass

    def place_title(self, mask, imgs, y):
        """Auto-place a title above the head with a slight overlap (like the reel).
        Shrinks it when headroom is short; falls back to drawing in front."""
        self.occlude = True
        if y is not None or mask is None:
            self.cy = self.H * (y if y is not None else 0.17); return imgs
        ink = max(i.getbbox()[3] - i.getbbox()[1] for i in imgs)
        line = ink / getattr(imgs[0], "nlines", 1)
        head, lim = head_top(mask), self.H * 0.06
        if head is None:
            self.cy = self.H * 0.17; return imgs
        over = self.overlap * line                   # how much of the last line hides behind the head
        s = min(1.0, (head - lim) / (ink - over))
        if s < 0.55:                        # no headroom: lower third, in front of the speaker
            self.occlude = False; self.cy = self.H * 0.72; return imgs
        self.cy = head + over * s - ink * s / 2
        return [scaled(i, s) for i in imgs]
    def active(self, t): return self.start <= t < self.end
    def plates(self, B, S, t, mask): return B, S          # background / subject plates (float32)
    def behind(self, canvas, t): pass                      # layers behind the speaker
    def front(self, canvas, t): pass                       # layers in front


class Strike(Effect):
    needs_mask = True
    def __init__(self, W, H, text, at, swap=None, strike_at=None, swap_at=None, dur=None, y=None, color="#F2ECE2", line="#E53935",
                 front_first=False, overlap=None, **o):
        super().__init__(W, H)
        self.front_first = bool(front_first)   # first word on the face (in front), swap word behind the head
        if overlap is not None: self.overlap = overlap
        self.start = at; self.strike_at = strike_at or at + 0.8
        self.swap_at = (swap_at or self.strike_at + 0.55) if swap else None
        self.end = at + dur if dur else (self.swap_at or self.strike_at) + 1.6
        self.y = y; self.rtl = bool(HEB.search(text))
        t1, f1 = fit_title(text, W, H)
        self.a = text_block(t1, f1, hex_rgb(color) + (255,), tight=True)
        self.b = text_block(*fit_title(swap, W, H), hex_rgb(color) + (255,), tight=True) if swap else None
        self.line = hex_rgb(line); self.lw = max(6, int(f1.size * 0.11))

    def setup(self, mask):
        imgs = self.place_title(mask, [self.a] + ([self.b] if self.b else []), self.y)
        if imgs[0].size != self.a.size: self.lw = max(4, int(self.lw * imgs[0].width / self.a.width))
        self.a = imgs[0]; self.b = imgs[1] if self.b else None
        self.cy_a = self.cy
        if self.front_first:
            if mask is not None:
                cx, cy, r = head_box(mask); self.cy_a = cy + r * 0.15
            sh = Image.new("RGBA", self.a.size, (0, 0, 0, 0))
            sh.putalpha(self.a.getchannel("A").filter(ImageFilter.GaussianBlur(max(4, self.a.height // 14))).point(lambda v: int(v * 0.75)))
            sh.alpha_composite(self.a); self.a = sh

    def _struck(self, p):
        img = self.a.copy(); d = ImageDraw.Draw(img)
        if p > 0:
            pad = int(img.height * 0.12); y0, y1 = img.height * 0.53, img.height * 0.47
            xa, xb = (img.width - pad, pad) if self.rtl else (pad, img.width - pad)
            xe = xa + (xb - xa) * p; ye = y0 + (y1 - y0) * p
            d.line([(xa, y0), (xe, ye)], fill=self.line + (255,), width=self.lw)
            for (x, y) in ((xa, y0), (xe, ye)):
                d.ellipse([x - self.lw / 2, y - self.lw / 2, x + self.lw / 2, y + self.lw / 2], fill=self.line + (255,))
        return img

    def _draw_a(self, c, t, out):
        if self.swap_at and t >= self.swap_at:
            q = prog(t, self.swap_at, 0.12)
            if q < 1: paste_center(c, with_alpha(scaled(self._struck(1), 1 - 0.3 * q), 1 - q), self.W / 2, self.cy_a)
            return
        p = prog(t, self.start, 0.28)
        img = self._struck(ease_out_cubic(prog(t, self.strike_at, 0.25)))
        paste_center(c, with_alpha(scaled(img, 1.25 - 0.25 * ease_out_back(p)), min(1, p * 2.5) * out), self.W / 2, self.cy_a)

    def _draw_b(self, c, t, out):
        if self.swap_at and t >= self.swap_at:
            p = prog(t, self.swap_at, 0.28)
            paste_center(c, with_alpha(scaled(self.b, 0.6 + 0.4 * ease_out_back(p)), min(1, p * 3) * out), self.W / 2, self.cy)

    def behind(self, c, t):
        out = 1 - prog(t, self.end - 0.2, 0.2)
        self._draw_b(c, t, out)
        if not self.front_first: self._draw_a(c, t, out)

    def front(self, c, t):
        if self.front_first: self._draw_a(c, t, 1 - prog(t, self.end - 0.2, 0.2))


class Echo(Effect):
    needs_mask = True
    def __init__(self, W, H, text, at, dur=2.5, y=None, color="#F2ECE2", copies=4, linger=False, **o):
        super().__init__(W, H); self.start, self.end, self.y = at, at + dur, y
        self.linger = bool(linger)   # keep the outline copies on screen until the effect ends
        t, f = fit_title(text, W, H)
        rgb = hex_rgb(color); sw = max(2, f.size // 45)
        self.solid = text_block(t, f, rgb + (255,), tight=True)
        self.ghost = text_block(t, f, (0, 0, 0, 0), stroke=sw, stroke_fill=rgb + (255,), tight=True)
        self.n = copies

    def setup(self, mask):
        self.solid, self.ghost = self.place_title(mask, [self.solid, self.ghost], self.y)

    def behind(self, c, t):
        rel = t - self.start; out = 1 - prog(t, self.end - 0.25, 0.25)
        gap = self.solid.height * 0.38
        for k in range(self.n, 0, -1):                      # echoes burst out, then fade
            p = ease_out_cubic(prog(rel, 0.05 * k, 0.45))
            if self.linger:
                p *= 1 + 0.04 * math.sin(rel * 3.2 + k)          # gentle breathing while they stay
                a = (1 - k / (self.n + 1)) * 0.85
            else:
                a = (1 - prog(rel, 0.35 + 0.06 * k, 0.5)) * (1 - k / (self.n + 1))
            if a <= 0.01 or p <= 0: continue
            for sgn in (-1, 1):
                paste_center(c, with_alpha(self.ghost, a * out), self.W / 2, self.cy + sgn * gap * k * p * 0.55)
        p = prog(rel, 0, 0.3)
        paste_center(c, with_alpha(scaled(self.solid, 0.85 + 0.15 * ease_out_back(p)), min(1, p * 2.5) * out), self.W / 2, self.cy)


class Spotlight(Effect):
    needs_mask = True
    def __init__(self, W, H, text, at, dur=2.5, y=None, color="#FF5A36", dim=0.28, **o):
        super().__init__(W, H); self.start, self.end, self.y, self.dim = at, at + dur, y, dim
        t, f = fit_title(text, W, H)
        rgb = hex_rgb(color); core = tuple(min(255, int(v * 0.35 + 255 * 0.65)) for v in rgb)
        base = text_block(t, f, rgb + (255,), tight=True)
        glow = Image.new("RGBA", (base.width + W // 3, base.height + W // 3), (0, 0, 0, 0))
        g = glow.copy(); g.alpha_composite(base, (W // 6, W // 6))
        for r, a in ((W // 18, 0.9), (W // 40, 1.0), (W // 90, 1.0)):
            glow.alpha_composite(with_alpha(g.filter(ImageFilter.GaussianBlur(r)), a))
        glow.alpha_composite(text_block(t, f, core + (255,), tight=True), (W // 6, W // 6))
        self.glow, self.base = glow, base
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        self.vign = np.clip(1 - (((xx - W / 2) / (W * 0.75)) ** 2 + ((yy - H * 0.45) / (H * 0.6)) ** 2), 0.15, 1)[..., None]
        self.yy, self.xx = yy, xx

    def setup(self, mask):   # place by the glyphs, not the glow margin
        s = self.place_title(mask, [self.base], self.y)[0].width / self.base.width
        self.glow = scaled(self.glow, s)

    def _level(self, t):
        return ease_out_cubic(prog(t, self.start, 0.35)) * (1 - ease_out_cubic(prog(t, self.end - 0.3, 0.3)))

    def plates(self, B, S, t, mask):
        e = self._level(t)
        if e <= 0: return B, S
        cool = np.array([0.85, 0.92, 1.1], np.float32)
        B = B * (1 - e) + B * self.dim * self.vign * cool * e
        cx, cy, r = head_box(mask)
        light = np.exp(-(((self.xx - cx) ** 2 + (self.yy - cy - r) ** 2) / (2 * (r * 2.2) ** 2)))[..., None]
        warm = np.array([1.1, 1.0, 0.88], np.float32)
        S = S * (1 - e) + S * (0.55 + 0.6 * light) * warm * e
        return np.clip(B, 0, 255), np.clip(S, 0, 255)

    def behind(self, c, t):
        rel = t - self.start
        flick = 1.0 if rel > 0.45 else [0, 1, 0.2, 1, 0.5, 1, 1, 0.7, 1, 1][int(rel / 0.045) % 10]
        paste_center(c, with_alpha(self.glow, flick * self._level(t) ** 0.5), self.W / 2, self.cy)


class FreezeMark(Effect):
    def __init__(self, W, H, at, hold=1.5, x=None, y=None, r=None, label=None, color="#FF3B30", zoom=1.07, **o):
        super().__init__(W, H); self.start, self.end, self.zoom = at, at + hold, zoom
        self.target = (x * W, y * H, r * W) if x is not None and y is not None else None
        self.r_frac, self.col, self.label, self.frozen = r, hex_rgb(color), label, None
        self.needs_mask = self.target is None; self.aspect = 0.9

    def freeze(self, frame, mask):
        if self.frozen is None:
            self.frozen = frame.copy()
            if self.target is None:
                fb = face_box(frame)
                if fb:
                    cx, cy, rx, ry = fb; self.target = (cx, cy, rx); self.aspect = ry / rx
                else:
                    cx, cy, r = head_box(mask); self.target = (cx, cy, (self.r_frac * self.W) if self.r_frac else r * 1.05)
        return self.frozen

    def _zoom_xy(self, x, y, z):
        cx, cy = self.target[0], self.target[1]
        return cx + (x - cx) * z, cy + (y - cy) * z

    def plates(self, B, S, t, mask):
        z = 1 + (self.zoom - 1) * ease_out_cubic(prog(t, self.start, 0.3))
        img = Image.fromarray(B.astype(np.uint8))
        if z > 1.001:
            cx, cy = self.target[0], self.target[1]
            w, h = self.W / z, self.H / z
            x0 = clamp(cx - (cx / self.W) * w, 0, self.W - w); y0 = clamp(cy - (cy / self.H) * h, 0, self.H - h)
            self._crop = (x0, y0, z)
            img = img.crop((int(x0), int(y0), int(x0 + w), int(y0 + h))).resize((self.W, self.H), Image.BICUBIC)
        else:
            self._crop = (0, 0, 1)
        a = np.asarray(img, np.float32); g = a.mean(2, keepdims=True)
        a = (a * 0.62 + g * 0.38) * 0.9
        f = 1 - prog(t, self.start, 0.14)
        a = a * (1 - f * 0.7) + 255 * f * 0.7
        return a, a

    def front(self, c, t):
        x0, y0, z = self._crop
        cx, cy, r = (self.target[0] - x0) * z, (self.target[1] - y0) * z, self.target[2] * z
        p = ease_out_cubic(prog(t, self.start + 0.18, 0.4))
        if p > 0:
            d = ImageDraw.Draw(c); pts = []; n = 90
            for i in range(int(n * p) + 1):
                a = -math.pi * 0.6 + 2.15 * math.pi * i / n
                rr = r * (1 + 0.06 * math.sin(3 * a + 1) + 0.03 * i / n)
                pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a) * self.aspect))
            if len(pts) > 1:
                d.line(pts, fill=self.col + (255,), width=max(6, self.W // 110), joint="curve")
        if self.label:
            q = prog(t, self.start + 0.45, 0.25)
            if q > 0:
                f = ImageFont.truetype(font_file(self.label, "ui", 900), self.W // 15)
                lab = text_block(self.label, f, (255, 255, 255, 255), stroke=self.W // 160, stroke_fill=(0, 0, 0, 255))
                ry = r * self.aspect
                ly = cy + ry + lab.height * 0.6 if cy + ry + lab.height < self.H * 0.85 else cy - ry - lab.height * 0.6
                paste_center(c, with_alpha(scaled(lab, 0.8 + 0.2 * ease_out_back(q)), q), cx, ly)


class PinnedComment(Effect):
    def __init__(self, W, H, user, text, at, dur=4.0, y=None, label=None, avatar_color="#8E5CF7", **o):
        super().__init__(W, H); self.start, self.end, self.y = at, at + dur, y
        self.needs_mask = y is None
        rtl = bool(HEB.search(text)); self.rtl = rtl
        label = label or (f"תגובה ל-@{user}" if rtl else f"Replying to @{user}")
        cw = int(W * 0.64); s = W / 1080
        fb = ImageFont.truetype(font_file(text, "ui", 700), int(44 * s)); fs = ImageFont.truetype(font_file(label, "ui", 400), int(30 * s))
        fa = ImageFont.truetype(font_file(user, "ui", 700), int(30 * s))
        av = int(58 * s); pad = int(30 * s); tw = cw - 2 * pad - av - int(18 * s)
        lines, cur = [], ""
        for w in text.split():
            cand = (cur + " " + w).strip(); tt, k = shape(cand)
            if fb.getbbox(tt, **k)[2] > tw and cur: lines.append(cur); cur = w
            else: cur = cand
        lines.append(cur); lines = lines[:4]
        body = text_block("\n".join(lines), fb, (17, 17, 17, 255), align="right" if rtl else "left", lh_mul=1.1)
        lab = text_block(label, fs, (130, 130, 130, 255), align="right" if rtl else "left")
        inner_h = max(av, lab.height * 0.62 + body.height * 0.82)
        ch = int(inner_h + 2 * pad * 0.8)
        card = Image.new("RGBA", (cw + 80, ch + 80), (0, 0, 0, 0))
        sh = Image.new("RGBA", card.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle([40, 52, 40 + cw, 52 + ch], int(34 * s), fill=(0, 0, 0, 110))
        card.alpha_composite(sh.filter(ImageFilter.GaussianBlur(int(18 * s))))
        d = ImageDraw.Draw(card); d.rounded_rectangle([40, 40, 40 + cw, 40 + ch], int(34 * s), fill=(255, 255, 255, 255))
        ax = 40 + cw - pad - av if rtl else 40 + pad; ay = 40 + int(pad * 0.8)
        d.ellipse([ax, ay, ax + av, ay + av], fill=hex_rgb(avatar_color) + (255,))
        ini = user[:1].upper(); d.text((ax + av / 2, ay + av / 2), ini, font=fa, fill="white", anchor="mm")
        gap = int(18 * s)
        tx = (ax - gap - lab.width + lab.pad) if rtl else (ax + av + gap - lab.pad)
        bx = (ax - gap - body.width + body.pad) if rtl else (ax + av + gap - body.pad)
        card.alpha_composite(lab, (int(tx), int(ay - lab.height * 0.3)))
        card.alpha_composite(body, (int(bx), int(ay + lab.height * 0.32)))
        self.card = card.rotate(2 if rtl else -2, resample=Image.BICUBIC, expand=True)
        self.cx = W - W * 0.06 - self.card.width / 2 if rtl else W * 0.06 + self.card.width / 2
        self.cy = H * (y if y is not None else 0.08) + self.card.height / 2

    def setup(self, mask):
        if self.y is not None or mask is None: return
        head, ch = head_top(mask), self.card.height
        if head is None: return
        top = min(self.H * 0.08, head + ch * 0.15 - ch)      # sit in the headroom, touching the hair
        self.cy = (top if top >= self.H * 0.035 else self.H * 0.58) + ch / 2

    def front(self, c, t):
        p = prog(t, self.start, 0.35); out = 1 - prog(t, self.end - 0.25, 0.25)
        paste_center(c, with_alpha(scaled(self.card, 0.8 + 0.2 * ease_out_back(p)), min(1, p * 3) * out), self.cx, self.cy)


FX = {"strike": Strike, "echo": Echo, "spotlight": Spotlight, "freeze-mark": FreezeMark, "pinned-comment": PinnedComment}


# ---------------------------------------------------------------- video io
def probe(path):
    j = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                   "stream=width,height,avg_frame_rate:stream_side_data=rotation:stream_tags=rotate",
                                   "-of", "json", path], capture_output=True, text=True, check=True).stdout)["streams"][0]
    W, H = j["width"], j["height"]
    rot = abs(int(float(j.get("tags", {}).get("rotate", 0) or 0)))
    for sd in j.get("side_data_list", []) or []:
        rot = abs(int(float(sd.get("rotation", rot))))
    if rot in (90, 270): W, H = H, W
    n, d = j["avg_frame_rate"].split("/")
    fps = round(float(n) / float(d), 3) if float(d) else 30.0
    return W, H, fps if 10 < fps < 121 else 30.0


def render(src, dst, specs, seg="auto", crf=17):
    W, H, fps = probe(src)
    effects = [FX[s["fx"]](W, H, **{k: v for k, v in s.items() if k != "fx"}) for s in specs]
    segm = Segmenter(seg) if any(e.needs_mask for e in effects) else None
    dec = subprocess.Popen(["ffmpeg", "-v", "error", "-i", src, "-vf", f"fps={fps}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
                            "-i", src, "-map", "0:v", "-map", "1:a?", "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
                            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", dst], stdin=subprocess.PIPE)
    size, i = W * H * 3, 0
    while True:
        buf = dec.stdout.read(size)
        if len(buf) < size: break
        t = i / fps; i += 1
        act = [e for e in effects if e.active(t)]
        if not act:
            enc.stdin.write(buf); continue
        frame = np.frombuffer(buf, np.uint8).reshape(H, W, 3)
        mask = segm(frame) if segm and any(e.needs_mask for e in act) else None
        for e in act:
            if isinstance(e, FreezeMark):
                frame = e.freeze(frame, mask if mask is not None else (segm(frame) if segm else np.ones((H, W), np.float32)))
                if mask is not None: mask = segm(frame, smooth=False)
        B = S = frame.astype(np.float32)
        for e in act:
            if not getattr(e, "_ready", False): e.setup(mask); e._ready = True
        for e in act: B, S = e.plates(B, S, t, mask)
        canvas = Image.fromarray(B.astype(np.uint8)).convert("RGBA")
        for e in act:
            if e.occlude: e.behind(canvas, t)
        out = np.asarray(canvas.convert("RGB"), np.float32)
        if mask is not None and any(e.needs_mask and not isinstance(e, FreezeMark) for e in act):
            m = mask[..., None]; out = out * (1 - m) + S * m   # speaker back on top of the text
        canvas = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)).convert("RGBA")
        for e in act:
            if not e.occlude: e.behind(canvas, t)
            e.front(canvas, t)
        enc.stdin.write(np.asarray(canvas.convert("RGB"), np.uint8).tobytes())
    enc.stdin.close(); enc.wait(); dec.wait()
    if enc.returncode: sys.exit("ffmpeg encode failed")
    print(json.dumps({"out": dst, "frames": i, "fps": fps, "size": [W, H], "seg": segm.kind if segm else None}))


def words(src, lang=None, model=None):
    from faster_whisper import WhisperModel
    model = model or ("ivrit-ai/whisper-large-v3-turbo-ct2" if lang == "he" else "small")
    try:
        m = WhisperModel(model, device="cpu", compute_type="int8")
    except Exception:
        m = WhisperModel("large-v3-turbo" if lang == "he" else "small", device="cpu", compute_type="int8")
    segs, _ = m.transcribe(src, language=lang, word_timestamps=True)
    for s in segs:
        for w in s.words:
            print(json.dumps({"word": w.word.strip(), "start": round(w.start, 2), "end": round(w.end, 2)}, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    w = sp.add_parser("words"); w.add_argument("src"); w.add_argument("--lang"); w.add_argument("--model")
    p = sp.add_parser("plan"); p.add_argument("src"); p.add_argument("dst"); p.add_argument("plan")
    p.add_argument("--seg", default="auto"); p.add_argument("--crf", type=int, default=17)
    for name in FX:
        e = sp.add_parser(name); e.add_argument("src"); e.add_argument("dst")
        e.add_argument("--seg", default="auto"); e.add_argument("--crf", type=int, default=17)
        for a in ("text", "swap", "user", "label", "color"): e.add_argument("--" + a)
        for a in ("at", "dur", "strike-at", "swap-at", "hold", "x", "y", "r"): e.add_argument("--" + a, type=float)
    a = ap.parse_args()
    if a.cmd == "words": return words(a.src, a.lang, a.model)
    if a.cmd == "plan":
        return render(a.src, a.dst, json.load(open(a.plan, encoding="utf-8")), a.seg, a.crf)
    spec = {k.replace("-", "_"): v for k, v in vars(a).items() if v is not None and k not in ("cmd", "src", "dst", "seg", "crf")}
    render(a.src, a.dst, [dict(fx=a.cmd, **spec)], a.seg, a.crf)


if __name__ == "__main__":
    main()
