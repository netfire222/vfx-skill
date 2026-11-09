---
name: vfx
description: Reel VFX pack - /vfx strike, echo, spotlight, freeze-mark, pinned-comment. Adds animated titles behind the speaker, strike-and-swap words, neon spotlight, freeze + face circle and comment cards to talking-head videos (Hebrew + English). Optional /vfx showcase wraps the result in a Claude-app UI with typed commands, sound effects and a CTA.
---

# /vfx - VFX pack for talking-head reels

Big titles are drawn **behind the speaker** (person segmentation) and auto-placed above the head. Full Hebrew/RTL support.

| Command | What it does |
|---|---|
| `/vfx strike` | Big word above the head -> red line strikes it -> swaps to a new word |
| `/vfx echo` | Big title pops in with outline echo copies bursting out |
| `/vfx spotlight` | Background goes dark, warm light on the speaker, flickering neon title |
| `/vfx freeze-mark` | Freeze + flash + punch-in + hand-drawn red circle around the face (+ optional label) |
| `/vfx pinned-comment` | "Reply to comment" card pops in at the top |
| `/vfx plan` | Several effects in one render |
| `/vfx showcase` | Wraps a rendered clip in a Claude-app UI: typed commands, "Edited with /vfx X" header, typing + effect sounds, ending CTA |

## Inputs
- The video (vertical 9:16 talking head works best) and, per effect, the exact texts and timing.
  Never invent texts the user did not give; ask once if missing. Timing can come from a trigger word (see `words`).
- Save output next to the source as `<name>_vfx.mp4`.

## Setup (once)
- Scripts live next to this file: `scripts/vfx.py`, `scripts/compose.py` (call them by full path).
- Needs `ffmpeg`, Node/npm (fonts + segmentation model are fetched once with `npm pack` into ~/.cache/vfx) and
  `pip install numpy pillow fonttools python-bidi ai-edge-litert "opencv-python-headless<5"`.
  Optional: `pip install rembg onnxruntime` (cleaner hair edges, used automatically), `pip install faster-whisper` (word timing).

## Workflow
1. `ffprobe` the clip. Little headroom above the head -> titles drop to the lower third automatically; suggest reframing.
2. Timing from speech: `python3 scripts/vfx.py words clip.mp4 --lang he` -> `{word,start,end}` lines.
3. Render:
   ```
   python3 scripts/vfx.py strike in.mp4 out.mp4 --text "משעמם" --swap "מרתק" --at 2.1 --strike-at 2.8 --swap-at 3.3
   python3 scripts/vfx.py echo in.mp4 out.mp4 --text "IN-APP BROWSER" --at 5 --dur 2.5
   python3 scripts/vfx.py spotlight in.mp4 out.mp4 --text "AI SLOP" --at 13 --dur 2.5
   python3 scripts/vfx.py freeze-mark in.mp4 out.mp4 --at 9.5 --hold 1.5 --label "תסתכלו כאן"
   python3 scripts/vfx.py pinned-comment in.mp4 out.mp4 --user someone --text "..." --at 17 --dur 4
   python3 scripts/vfx.py plan in.mp4 out.mp4 plan.json      # [{"fx":"strike","text":..,"at":..}, ...]
   ```
   Strike variant (plan.json only): `"front_first": true` puts the first word ON the face, in front of the speaker,
   and the swap word BEHIND the head (e.g. "מלפנים" -> "מאחור"); `"overlap": 0.45` hides more of it behind the head.
   Echo variant (plan.json): `"linger": true` keeps the outline copies on screen (gently breathing) until the effect ends.
   Options: `--y` (fixed title height, fraction of frame; raise it if the head hides letters), `--color`,
   freeze-mark `--x --y --r` to circle something else, `--seg fast|quality`, `--crf`.
4. Showcase (optional): `python3 scripts/compose.py fx.mp4 final.mp4 schedule.json`
   ```
   {"intro": 2.4, "cta": 3.2,
    "cmds": [{"cmd": "strike", "send": 0.0, "desc": "Say it, strike it, swap it", "sfx": [["swish", 0.9], ["pop", 1.5]]},
             {"cmd": "echo", "send": 2.75, "desc": "Big title, echo burst", "sfx": [["boom", 2.8]]}],
    "cta_lines": ["רוצים את הסקיל", "של 5 הפקודות?"], "cta_button": "תגיבו \"סקיל\""}
   ```
   `send` = clip second the command is sent (set each effect's `at` ~0.05s after it). First command is typed in the intro.
   Sounds: key, send, whoosh, swish, pop, boom, shutter, power, ding, chime.
5. Verify: grab 2-3 frames per effect (`ffmpeg -ss T -i out.mp4 -frames:v 1 f.png`), look at them (text readable,
   face visible, Hebrew right-to-left, nothing cut), fix and re-render. Then deliver with one line per effect.
