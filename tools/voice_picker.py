#!/usr/bin/env python3
"""Glove Up voice picker.

Finds ElevenLabs voices that could work as a boxing coach and has each one
read the same coach line, then builds voice-picker.html so you can compare
them side by side.

The API key is read from the ELEVENLABS_API_KEY environment variable and is
never written to disk. Output goes to ~/glove-up-voices (outside the repo).
"""
import html, json, os, sys, time, urllib.parse, urllib.request, urllib.error

KEY = os.environ.get("ELEVENLABS_API_KEY", "").strip()
if not KEY:
    sys.exit("Set ELEVENLABS_API_KEY first.")

API = "https://api.elevenlabs.io"
OUT = os.path.expanduser("~/glove-up-voices")
LINE = "Round one! Jab, cross, left hook. Hands up! Slip... roll. Burnout, let's go, let's go!"
SEARCHES = ["boxing", "boxing coach", "coach", "trainer", "drill sergeant",
            "gym", "fitness", "motivational", "sports", "announcer", "intense"]
MAX_LIBRARY = 14   # library voices to sample
MODEL = "eleven_multilingual_v2"
SPEAK = "--speak" in sys.argv   # default: free previews only, 0 credits

os.makedirs(OUT, exist_ok=True)


def req(path, data=None, raw=False):
    url = path if path.startswith("http") else API + path
    body = json.dumps(data).encode() if data is not None else None
    r = urllib.request.Request(url, data=body, method="POST" if body else "GET")
    if url.startswith(API):
        r.add_header("xi-api-key", KEY)
    if body:
        r.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(r, timeout=60) as resp:
        b = resp.read()
    return b if raw else json.loads(b)


def safe(s):
    return "".join(c if c.isalnum() else "_" for c in s)[:40]


voices = []  # dicts: id, name, source, desc, preview

# 0) Show credit usage (free call)
try:
    sub = req("/v1/user/subscription")
    used, lim = sub.get("character_count", 0), sub.get("character_limit", 0)
    reset = sub.get("next_character_count_reset_unix")
    when = time.strftime("%b %d", time.localtime(reset)) if reset else "?"
    print(f"ElevenLabs plan: {sub.get('tier','?')} | used {used:,} of {lim:,} characters | {lim-used:,} left | resets {when}")
except urllib.error.HTTPError as e:
    print(f"(Couldn't read usage: {e.code} — key may lack the user_read permission)")

# 1) Voices already in your account (premade + any you added)
try:
    for v in req("/v1/voices").get("voices", []):
        lab = v.get("labels") or {}
        voices.append({"id": v["voice_id"], "name": v.get("name", "?"),
                       "source": "Your account (" + (v.get("category") or "") + ")",
                       "desc": ", ".join(x for x in [lab.get("gender"), lab.get("age"), lab.get("accent"),
                                                      lab.get("descriptive") or lab.get("description"),
                                                      lab.get("use_case")] if x),
                       "preview": v.get("preview_url"), "rank": 0})
except urllib.error.HTTPError as e:
    sys.exit(f"API key rejected or account error ({e.code}). Check the key.")

# 2) Voice Library search for coach-type voices
seen = {v["id"] for v in voices}
lib = []
for term in SEARCHES:
    q = urllib.parse.urlencode({"search": term, "language": "en", "page_size": 30,
                                "sort": "usage_character_count_1y"})
    try:
        res = req("/v1/shared-voices?" + q)
    except urllib.error.HTTPError as e:
        print(f"  search '{term}' failed ({e.code}), skipping")
        continue
    for v in res.get("voices", []):
        if v["voice_id"] in seen:
            continue
        seen.add(v["voice_id"])
        lib.append({"id": v["voice_id"], "name": v.get("name", "?"),
                    "source": f"Voice Library · found by '{term}'",
                    "desc": ", ".join(x for x in [v.get("gender"), v.get("age"), v.get("accent"),
                                                   v.get("descriptive"), v.get("use_case")] if x)
                            + (" — " + v["description"][:160] if v.get("description") else ""),
                    "preview": v.get("preview_url"),
                    "rank": v.get("usage_character_count_1y") or v.get("cloned_by_count") or 0})
    time.sleep(0.2)
lib.sort(key=lambda v: -v["rank"])
voices += lib[:MAX_LIBRARY]

print("Mode: " + ("coach line (uses credits)" if SPEAK else "FREE previews only (0 credits)"))
print(f"Sampling {len(voices)} voices with the coach line ({len(LINE)} characters each)...")

# 3) Have each voice read the coach line (falls back to its own preview if not allowed)
for i, v in enumerate(voices, 1):
    fn = f"{i:02d}_{safe(v['name'])}.mp3"
    path = os.path.join(OUT, fn)
    v["file"], v["kind"] = None, ""
    try:
        if not SPEAK:
            raise urllib.error.HTTPError(None, 0, "free mode", None, None)
        audio = req(f"/v1/text-to-speech/{v['id']}?output_format=mp3_44100_128",
                    {"text": LINE, "model_id": MODEL,
                     "voice_settings": {"stability": 0.35, "similarity_boost": 0.8, "style": 0.45}},
                    raw=True)
        open(path, "wb").write(audio)
        v["file"], v["kind"] = fn, "Coach line"
        print(f"  {i:2d}. {v['name']}: ok")
    except urllib.error.HTTPError as e:
        if v.get("preview"):
            try:
                open(path, "wb").write(req(v["preview"], raw=True))
                v["file"], v["kind"] = fn, ("Voice's own preview" if not SPEAK else "Voice's own preview (coach line not allowed for this voice)")
                print(f"  {i:2d}. {v['name']}: preview saved")
            except Exception:
                print(f"  {i:2d}. {v['name']}: failed ({e.code})")
        else:
            print(f"  {i:2d}. {v['name']}: failed ({e.code})")
    time.sleep(0.3)

# 4) Build the picker page
rows = []
for i, v in enumerate([v for v in voices if v["file"]], 1):
    rows.append(f"""<div class="v"><div class="top"><b>{i}. {html.escape(v['name'])}</b>
<span>{html.escape(v['source'])}</span></div>
<div class="d">{html.escape(v['desc'] or '')}</div>
<audio controls preload="none" src="{v['file']}"></audio>
<div class="k">{html.escape(v['kind'])} · voice ID <code>{v['id']}</code></div></div>""")
page = f"""<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Glove Up voice picker</title>
<style>body{{font:16px -apple-system,sans-serif;background:#0b1410;color:#eef5f0;max-width:760px;margin:0 auto;padding:16px}}
h1{{font-size:24px}}.v{{background:#13211a;border:1px solid #2a4034;border-radius:14px;padding:14px;margin:10px 0}}
.top{{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap}}.top span,.k{{color:#9fb3a7;font-size:13px}}
.d{{color:#cfdcd4;font-size:14px;margin:6px 0}}audio{{width:100%;margin:6px 0}}code{{color:#f2c230}}</style>
<h1>🥊 Glove Up voice picker</h1><p>Line: “{html.escape(LINE)}”</p><p>Tell Claude the <b>number and name</b> (or voice ID) of the one you like, and one for the kids if you want a different voice for them.</p>
{''.join(rows)}"""
open(os.path.join(OUT, "voice-picker.html"), "w").write(page)
print("\nDone. Opening", os.path.join(OUT, "voice-picker.html"))
