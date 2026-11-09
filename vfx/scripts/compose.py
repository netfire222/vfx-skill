#!/usr/bin/env python3
"""compose.py - wrap a /vfx-rendered clip in a Claude-app style UI:
typed /vfx commands, "Edited with /vfx X" header, ending CTA, and a full sound design.

  compose.py FX.mp4 OUT.mp4 schedule.json
schedule.json: {"intro": 2.4, "cta": 3.0,
                "cmds": [{"cmd": "strike", "send": 0.0, "desc": "Say it, strike it, swap it",
                          "sfx": [["swish", 0.9], ["pop", 1.5]]}, ...],
                "cta_lines": ["רוצים את הסקיל", "של 5 הפקודות?"], "cta_button": "תגיבו \\"סקיל\\""}
Times in "cmds" are clip times (seconds into FX.mp4). The first command is typed during the intro.
"""
import json, math, os, subprocess, sys, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vfx import heebo, npm_fetch, shape, ease_out_back, ease_out_cubic, prog, paste_center, with_alpha, scaled  # noqa

W, H, FPS, SR = 1080, 1920, 30, 48000
BG, CARD, LINE = (24, 23, 21), (38, 38, 36), (62, 61, 58)
TXT, MUTED, ACC, CMD, OK = (236, 234, 228), (156, 154, 146), (217, 119, 87), (232, 112, 96), (92, 186, 120)
CARD_BOX = (105, 205, 975, 1745)          # video card (x0, y0, x1, y1) -> 870x1540
INPUT_BOX = (60, 1772, 1020, 1888)
CHAR_T = 0.05                              # seconds per typed character


def mono(size, w=500): return ImageFont.truetype(npm_fetch("@fontsource/jetbrains-mono", f"files/jetbrains-mono-latin-{w}-normal.woff")[0], size)
def ui(size, w=500): return ImageFont.truetype(heebo(w), size)


def rounded(img, r):
    m = Image.new("L", img.size, 0); ImageDraw.Draw(m).rounded_rectangle([0, 0, img.width - 1, img.height - 1], r, fill=255)
    img = img.convert("RGBA"); img.putalpha(m); return img


def starburst(size, color=ACC):
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0)); d = ImageDraw.Draw(im); c = size / 2
    for k in range(12):
        a = k * math.pi / 6; r = size * (0.42 if k % 2 == 0 else 0.3)
        d.line([(c, c), (c + r * math.cos(a), c + r * math.sin(a))], fill=color + (255,), width=max(3, size // 12))
    return im


# ------------------------------------------------------------------ static chrome
def chrome(header_cmd=None, header_alpha=1.0):
    im = Image.new("RGBA", (W, H), BG + (255,)); d = ImageDraw.Draw(im)
    for i in range(3):                                         # hamburger
        d.rounded_rectangle([60, 70 + i * 18, 104, 76 + i * 18], 3, fill=MUTED)
    d.rounded_rectangle([400, 52, 680, 128], 38, fill=(34, 33, 31)); d.rounded_rectangle([545, 58, 674, 122], 32, fill=(58, 57, 54))
    f = ui(34, 500); d.text((472, 90), "Chat", font=f, fill=MUTED, anchor="mm"); d.text((610, 90), "Code", font=f, fill=TXT, anchor="mm")
    d.rounded_rectangle([968, 66, 1016, 114], 8, outline=MUTED, width=4)   # new-chat icon
    if header_cmd:
        hd = Image.new("RGBA", (W, 70), (0, 0, 0, 0)); h = ImageDraw.Draw(hd)
        h.line([(108, 37), (120, 50), (142, 24)], fill=OK + (255,), width=6, joint="curve")
        fe, fm = ui(34, 500), mono(32, 500)
        h.text((160, 36), "Edited with", font=fe, fill=MUTED, anchor="lm")
        h.text((160 + fe.getlength("Edited with ") + 4, 36), f"/vfx {header_cmd}", font=fm, fill=CMD, anchor="lm")
        im.alpha_composite(with_alpha(hd, header_alpha), (0, 132))
    return im


def input_bar(im, typed="", caret=True, placeholder="Reply to Claude...", rtl=False):
    d = ImageDraw.Draw(im); x0, y0, x1, y1 = INPUT_BOX
    d.rounded_rectangle(INPUT_BOX, 40, fill=CARD, outline=LINE, width=3)
    d.ellipse([x1 - 96, y0 + 22, x1 - 24, y0 + 94], fill=ACC)                     # send button
    cx, cy = x1 - 60, y0 + 58
    d.line([(cx, cy + 18), (cx, cy - 16)], fill="white", width=7); d.line([(cx - 15, cy - 2), (cx, cy - 17), (cx + 15, cy - 2)], fill="white", width=7, joint="curve")
    ty = (y0 + y1) / 2
    if not typed:
        d.text((x0 + 44, ty), placeholder, font=ui(38, 400), fill=MUTED, anchor="lm")
        if caret: d.rectangle([x0 + 40, ty - 24, x0 + 43, ty + 24], fill=TXT)
        return
    f = mono(40, 500); x = x0 + 44
    head, rest = (typed[:5], typed[5:]) if typed.startswith("/vfx ") else (typed, "")
    d.text((x, ty), head, font=f, fill=CMD, anchor="lm"); x += f.getlength(head)
    d.text((x, ty), rest, font=f, fill=TXT, anchor="lm"); x += f.getlength(rest)
    if caret: d.rectangle([x + 3, ty - 26, x + 6, ty + 26], fill=TXT)


def suggestion(im, cmd, desc, a):
    if a <= 0: return
    card = Image.new("RGBA", (960, 132), (0, 0, 0, 0)); d = ImageDraw.Draw(card)
    d.rounded_rectangle([0, 0, 959, 131], 30, fill=(46, 45, 43, 245), outline=LINE, width=2)
    d.rounded_rectangle([24, 24, 108, 108], 20, fill=(66, 44, 36)); card.alpha_composite(starburst(64), (34, 34))
    d.text((132, 46), f"/vfx {cmd}", font=mono(40, 700), fill=CMD, anchor="lm")
    d.text((132, 94), desc, font=ui(32, 400), fill=MUTED, anchor="lm")
    d.text((928, 66), "tab", font=ui(30, 400), fill=MUTED, anchor="rm")
    s = 0.92 + 0.08 * ease_out_back(a)
    paste_center(im, with_alpha(scaled(card, s), min(1, a * 2)), W / 2, 1620 + 30 * (1 - a))


# ------------------------------------------------------------------ CTA
def cta_layer(lines, button, t):
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    p1, p2 = prog(t, 0.1, 0.4), prog(t, 0.55, 0.4)
    panel_w, x1 = 900, W - 90
    f = ui(104, 900)
    blk = Image.new("RGBA", (panel_w, 300), (0, 0, 0, 0)); d = ImageDraw.Draw(blk)
    for i, ln in enumerate(lines):
        tt, k = shape(ln); d.text((panel_w - 10, 70 + i * 128), tt, font=f, fill=(255, 255, 255, 255), anchor="rm", **k)
    sh = blk.filter(ImageFilter.GaussianBlur(14)); sh = Image.eval(sh, lambda v: v)  # soft shadow
    shadow = Image.new("RGBA", blk.size, (0, 0, 0, 0)); shadow.putalpha(sh.getchannel("A").point(lambda v: int(v * 0.7)))
    if p1 > 0:
        y = 640 + 40 * (1 - ease_out_cubic(p1))
        lay.alpha_composite(with_alpha(shadow, p1), (x1 - panel_w, int(y) + 6)); lay.alpha_composite(with_alpha(blk, p1), (x1 - panel_w, int(y)))
    if p2 > 0:
        fb = ui(70, 900); tt, k = shape(button)
        bw = int(fb.getbbox(tt, **k)[2] - fb.getbbox(tt, **k)[0]) + 190
        btn = Image.new("RGBA", (bw + 40, 190), (0, 0, 0, 0)); d = ImageDraw.Draw(btn)
        d.rounded_rectangle([20, 20, bw + 20, 170], 75, fill=ACC + (255,))
        bx = bw - 40                                      # speech-bubble icon on the right (RTL)
        d.rounded_rectangle([bx - 52, 62, bx + 8, 112], 14, fill="white"); d.polygon([(bx - 40, 108), (bx - 46, 132), (bx - 22, 110)], fill="white")
        d.text((bx - 80, 95), tt, font=fb, fill="white", anchor="rm", **k)
        s = 0.6 + 0.4 * ease_out_back(p2)
        bimg = scaled(btn, s); lay.alpha_composite(with_alpha(bimg, min(1, p2 * 2)), (int(x1 - bimg.width + 20), int(960 + (190 - bimg.height) / 2)))
    return lay


# ------------------------------------------------------------------ audio
rng = np.random.default_rng(7)
def env(n, a=0.002, d=0.05):
    t = np.arange(n) / SR; return np.minimum(1, t / max(a, 1e-4)) * np.exp(-t / d)
def noise(n): return rng.standard_normal(n)
def tone(f, n, d=0.2): t = np.arange(n) / SR; return np.sin(2 * np.pi * f * t) * env(n, 0.003, d)
def sweep(f0, f1, n, d=0.08):
    t = np.arange(n) / SR; f = f0 + (f1 - f0) * t / (n / SR); return np.sin(2 * np.pi * np.cumsum(f) / SR) * env(n, 0.002, d)
def hp(x): return np.diff(x, prepend=0)
def lp(x, k=8): return np.convolve(x, np.ones(k) / k, mode="same")

def sfx(name):
    n = lambda s: int(SR * s)
    if name == "key":
        x = hp(noise(n(0.03))) * env(n(0.03), 0.0005, 0.006) * 0.5 + tone(rng.uniform(140, 190), n(0.03), 0.01) * 0.6
        return x * rng.uniform(0.5, 0.9)
    if name == "send": return sweep(700, 1500, n(0.09), 0.05) * 0.5 + hp(noise(n(0.09))) * env(n(0.09), 0.001, 0.01) * 0.2
    if name == "whoosh":
        m = n(0.45); t = np.arange(m) / m; x = lp(noise(m), 6) * np.sin(np.pi * t) ** 2
        return x * 0.5
    if name == "swish":
        m = n(0.28); t = np.arange(m) / m; x = hp(noise(m)) * np.sin(np.pi * t) ** 1.5 * (0.3 + t)
        return x * 0.35
    if name == "pop": return sweep(500, 1300, n(0.12), 0.04) * 0.6
    if name == "boom":
        m = n(0.9); return (tone(55, m, 0.35) + 0.5 * tone(82, m, 0.2)) * 0.9 + lp(noise(m), 30) * env(m, 0.001, 0.08) * 0.4
    if name == "shutter":
        m = n(0.25); x = np.zeros(m)
        for off in (0, 0.07):
            i = int(off * SR); k = n(0.025); x[i:i + k] += hp(noise(k)) * env(k, 0.0003, 0.005)
        return x * 0.8 + tone(2400, m, 0.01) * 0.15
    if name == "power":
        m = n(0.9); t = np.arange(m) / SR
        buzz = np.sign(np.sin(2 * np.pi * 100 * t)) * 0.08 * (0.5 + 0.5 * (rng.random(m) > 0.4))
        return tone(48, m, 0.3) * 1.0 + buzz * np.exp(-t / 0.5)
    if name == "ding":
        m = n(0.9); return (tone(1318.5, m, 0.35) + 0.6 * tone(1760, m, 0.3)) * 0.35
    if name == "chime":
        m = n(1.4); x = np.zeros(m)
        for i, f in enumerate((1046.5, 1318.5, 1568, 2093)):
            o = int(i * 0.09 * SR); x[o:] += tone(f, m - o, 0.4)[: m - o] * 0.28
        return x
    raise KeyError(name)


def place(track, x, t):
    i = int(t * SR)
    if i >= len(track) or i < 0: return
    j = min(len(track), i + len(x)); track[i:j] += x[: j - i]


# ------------------------------------------------------------------ main
def main():
    src, dst, sched = sys.argv[1], sys.argv[2], json.load(open(sys.argv[3], encoding="utf-8"))
    intro, cta = sched.get("intro", 2.4), sched.get("cta", 3.0)
    cmds = sched["cmds"]
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", src], capture_output=True, text=True).stdout)
    total = intro + dur + cta; N = int(total * FPS)

    # typing windows in global time
    win = []
    for i, c in enumerate(cmds):
        text = f"/vfx {c['cmd']}"
        send = (intro - 0.55) if i == 0 else intro + c["send"]
        start = send - len(text) * CHAR_T - 0.25
        win.append((start, send, text, c))

    # ---------- audio
    track = np.zeros(int((total + 1) * SR))
    for start, send, text, c in win:
        for k in range(len(text)):
            place(track, sfx("key"), start + 0.12 + k * CHAR_T + rng.uniform(-0.01, 0.01))
        place(track, sfx("send"), send)
        for name, t in c.get("sfx", []):
            place(track, sfx(name), intro + t)
    place(track, sfx("whoosh"), intro - 0.45)
    place(track, sfx("chime"), intro + dur + 0.15)
    place(track, sfx("pop"), intro + dur + 0.7)
    track = np.tanh(track * 1.2); track = track / max(1e-6, np.abs(track).max()) * 0.89
    wav = dst + ".wav"
    with wave.open(wav, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes((track * 32767).astype(np.int16).tobytes())

    # ---------- video
    x0, y0, x1, y1 = CARD_BOX; cw, ch = x1 - x0, y1 - y0
    dec = subprocess.Popen(["ffmpeg", "-v", "error", "-i", src, "-vf", f"fps={FPS},scale={cw}:{ch}:flags=lanczos", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", wav,
                            "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                            "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", dst], stdin=subprocess.PIPE)
    first = last = None
    sz = cw * ch * 3
    for fi in range(N):
        t = fi / FPS; ct = t - intro
        if 0 <= ct < dur:
            buf = dec.stdout.read(sz)
            if len(buf) == sz:
                last = Image.frombuffer("RGB", (cw, ch), buf)
                first = first or last
        elif ct < 0 and first is None:
            buf = dec.stdout.read(sz); first = last = Image.frombuffer("RGB", (cw, ch), buf)
        # header: last sent command
        hdr = None; ha = 1.0
        for start, send, text, c in win:
            if t >= send + 0.12: hdr = c["cmd"]; ha = ease_out_cubic(prog(t, send + 0.12, 0.25))
        im = chrome(hdr, ha)
        if ct < 0:                                             # intro: attached clip bubble -> expands into the card
            grow = ease_out_cubic(prog(t, intro - 0.4, 0.4))
            tw, th = int(300 + (cw - 300) * grow), int(300 * ch / cw + (ch - 300 * ch / cw) * grow)
            tx = int((W - 60 - 300) + (x0 - (W - 60 - 300)) * grow); ty = int(240 + (y0 - 240) * grow)
            thumb = rounded(first.resize((tw, th), Image.BICUBIC), int(28 + 8 * grow))
            im.alpha_composite(thumb, (tx, ty))
            if grow < 0.5:
                d = ImageDraw.Draw(im); d.rounded_rectangle([tx + 18, ty + th - 70, tx + 110, ty + th - 22], 14, fill=(0, 0, 0, 160))
                d.text((tx + 64, ty + th - 46), f"0:{int(dur):02d}", font=ui(30, 700), fill="white", anchor="mm")
        else:
            frame = last
            if ct >= dur:                                      # CTA: frozen, dimmed, blurred
                k = ease_out_cubic(prog(ct, dur, 0.4))
                frame = Image.blend(frame, frame.filter(ImageFilter.GaussianBlur(10)), k)
                frame = Image.eval(frame, lambda v, k=k: int(v * (1 - 0.45 * k)))
            im.alpha_composite(rounded(frame, 36), (x0, y0))
        # typing + suggestion
        typed, caret = "", (int(t * 2) % 2 == 0)
        for start, send, text, c in win:
            if start <= t < send:
                typed = text[: max(0, min(len(text), int((t - start - 0.12) / CHAR_T) + 1))]; caret = True
                suggestion(im, c["cmd"], c.get("desc", ""), prog(t, start + 0.12 + 4 * CHAR_T, 0.18))
        input_bar(im, typed, caret)
        if ct >= dur:
            im.alpha_composite(cta_layer(sched["cta_lines"], sched["cta_button"], ct - dur))
        enc.stdin.write(np.asarray(im.convert("RGB")).tobytes())
    enc.stdin.close(); enc.wait(); dec.kill()
    os.remove(wav)
    print(json.dumps({"out": dst, "seconds": round(total, 2), "frames": N}))


if __name__ == "__main__":
    main()
