#!/usr/bin/env python3
"""Record Glove Up coach clips with ElevenLabs.

Reads tools/phrases.json (what the coach says) and tools/voice_packs.json
(which voices), and writes audio/<pack>/<clip>.mp3 plus a manifest for the
app. Clips that already exist are skipped, so re-running only records
what's new (a new phrase or a new voice pack).

Usage:  python3 tools/record_voice.py            # all packs
        python3 tools/record_voice.py coach      # one pack
The API key comes from ELEVENLABS_API_KEY and is never saved.
"""
import json, os, re, sys, time, urllib.request, urllib.error

KEY = os.environ.get("ELEVENLABS_API_KEY", "").strip()
if not KEY:
    sys.exit("Set ELEVENLABS_API_KEY first.")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PHRASES = json.load(open(os.path.join(ROOT, "tools", "phrases.json")))
PACKS = json.load(open(os.path.join(ROOT, "tools", "voice_packs.json")))
only = sys.argv[1:]
MODEL = "eleven_multilingual_v2"
SETTINGS = {"stability": 0.4, "similarity_boost": 0.8, "style": 0.4}


def slug(k):
    return re.sub(r"[^a-z0-9]+", "-", k.replace("'", "")).strip("-")


def tts(voice_id, text):
    r = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=mp3_44100_64",
        data=json.dumps({"text": text, "model_id": MODEL, "voice_settings": SETTINGS}).encode(),
        method="POST", headers={"xi-api-key": KEY, "Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=60) as resp:
        return resp.read()


chars = 0
for pack, cfg in PACKS.items():
    if only and pack not in only:
        continue
    out = os.path.join(ROOT, "audio", pack)
    os.makedirs(out, exist_ok=True)
    manifest = {}
    todo = [(k, t) for k, t in PHRASES.items() if not os.path.exists(os.path.join(out, slug(k) + ".mp3"))]
    print(f"{cfg['name']} ({pack}): {len(todo)} new clips, {sum(len(t) for _, t in todo)} characters")
    for k, t in PHRASES.items():
        f = slug(k) + ".mp3"
        path = os.path.join(out, f)
        if not os.path.exists(path):
            for attempt in range(3):
                try:
                    open(path, "wb").write(tts(cfg["voice_id"], t))
                    chars += len(t)
                    print(f"   ✓ {k}")
                    break
                except urllib.error.HTTPError as e:
                    msg = e.read().decode(errors="ignore")[:200]
                    if e.code == 429 and attempt < 2:
                        time.sleep(3); continue
                    sys.exit(f"   ✗ {k}: HTTP {e.code} {msg}")
            time.sleep(0.15)
        manifest[k] = f
    json.dump({"name": cfg["name"], "phrases": manifest}, open(os.path.join(out, "manifest.json"), "w"), indent=1)

# list of packs for the app (only ones that have been recorded)
packs = [{"id": p, "name": c["name"], "label": c["label"]} for p, c in PACKS.items()
         if os.path.exists(os.path.join(ROOT, "audio", p, "manifest.json"))]
json.dump(packs, open(os.path.join(ROOT, "audio", "packs.json"), "w"), indent=1)
print(f"\nDone. Used about {chars} characters. Packs ready: {', '.join(p['name'] for p in packs)}")
