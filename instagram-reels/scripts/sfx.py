"""Fetch real recorded SFX from the internet (never synthesized). Only CC0 / Public-Domain sources.
Chain per role: Freesound API (if FREESOUND_TOKEN) -> Wikimedia Commons -> Internet Archive (USC SSE, CC0)
-> GitHub CC0 pack (this skill's repo). Output: work/sfx/<role>.wav (trimmed, normalized) + work/sfx/credits.txt
usage: sfx.py role [role ...]"""
import os, re, sys, json, time, urllib.request, urllib.parse, wave
import numpy as np
from lib import wp, run

UA = {"User-Agent": "instagram-reels-skill/1.0 (open-source video editor; CC0 sfx lookup)"}
GH = "https://raw.githubusercontent.com/"
KI = GH + "ShadowBlip/OpenGamepadUI/main/assets/audio/interface/{}.ogg"      # Kenney Interface Sounds (CC0)
KR = GH + "godotengine/godot-benchmarks/main/supplemental/audio/{}.ogg"      # Kenney RPG Audio (CC0)
KM = GH + "iree-gd/iree.gd/main/sample/assets/audio/impact/{}.ogg"           # Kenney Impact Sounds (CC0)
PACK = GH + "uday629/instagram-shorts/main/sfx-pack/{}.mp3"                   # mirror of the above (CC0)
IA = "https://archive.org/download/SSE_Library_{}/{}"                          # USC SSE library (CC0)


def K(base, names, lic="Kenney.nl, CC0"):
    return ("url", [base.format(n) for n in names], lic)


def ia(c, f):
    return ("ia", [IA.format(c, f.replace(" ", "%20").replace(";", "%3B").replace("&", "%26"))], "USC SSE Library via Internet Archive, CC0")


def pk(role, n=3):
    return ("url", [PACK.format(f"{role}_{i}") for i in range(1, n + 1)], "instagram-shorts sfx-pack mirror, CC0")


# role: target seconds, search query, ordered sources, options (win = keep a time window, rev = reversed riser, alias)
ROLES = {
    "whoosh": (.7, "whoosh", [ia("SWOOSHES", "SWISH/SWSH_Processed swishes_CS_USC.mp3"), pk("whoosh"), K(KI, [f"maximize_00{i}" for i in range(1, 10)])], {}),
    "whoosh_soft": (.6, "swish cloth", [K(KR, ["cloth1", "cloth2", "cloth3", "cloth4"]), pk("whoosh_soft")], {}),
    "click": (.2, "mouse click", [K(KI, [f"click_00{i}" for i in range(1, 6)]), pk("click")], {}),
    "tick": (.2, "clock tick", [K(KI, ["tick_001", "tick_002", "tick_004"]), pk("tick")], {}),
    "tap": (.25, "tap", [K(KI, [f"select_00{i}" for i in range(1, 9)]), pk("tap")], {}),
    "pop": (.3, "pop", [K(KI, ["drop_001", "drop_002", "drop_003", "drop_004", "pluck_001", "pluck_002"]), pk("pop"),
                        ia("CARTOON", "POP/TOONPop_Comedy cartoon cork pop_CS_USC.mp3")], {}),
    "impact": (.9, "impact hit", [K(KM, [f"impactPunch_heavy_00{i}" for i in range(5)]), pk("impact")], {}),
    "impact_soft": (.9, "soft thud", [K(KM, [f"impactSoft_heavy_00{i}" for i in range(5)]), pk("impact_soft")], {}),
    "riser": (1.4, "riser", [ia("SWOOSHES", "WHOOSH/WHSH_Scifi swish by_CS_USC.mp3"), pk("riser", 2)], {"rev": 1}),
    "paper": (.7, "page turn", [K(KR, ["bookFlip1", "bookFlip2", "bookFlip3"]), pk("paper")], {}),
    "pencil": (1.0, "pencil writing", [], {"alias": "paper"}),
    "keyboard": (1.0, "keyboard typing", [], {"alias": "click"}),
    "typewriter": (1.0, "typewriter", [ia("COMMUNICATIONS", "TELEMETRY/COMTelm_Teletype or printing machine_CS_USC.mp3"), pk("typewriter", 1)], {"win": 1}),
    "camera": (.4, "camera shutter", [], {"alias": "click"}),
    "heartbeat": (1.8, "heartbeat", [ia("HUMAN", "HEARTBEAT/HMNHart_Human heartbeat_CS_USC.mp3"), pk("heartbeat", 1)], {"win": 1}),
    "breath": (.9, "breath", [], {"alias": "whoosh_soft"}),
    "phone_buzz": (.7, "phone vibration", [], {"alias": "glitch"}),
    "stamp": (.4, "stamp", [K(KM, [f"impactWood_heavy_00{i}" for i in range(5)]), K(KR, ["bookPlace1", "bookPlace2", "bookPlace3"]), pk("stamp")], {}),
    "glitch": (.4, "glitch", [K(KI, [f"glitch_00{i}" for i in range(1, 5)]), pk("glitch")], {}),
    "boing": (.6, "boing", [ia("CARTOON", "BOING/TOONBoing_Large spring snaps with a twang_CS_USC.mp3"), pk("boing", 1)], {}),
    "scratch": (.5, "scratch", [K(KI, [f"scratch_00{i}" for i in range(1, 6)]), pk("scratch")], {}),
    "door": (.6, "door", [K(KR, ["doorOpen_1", "doorOpen_2", "doorClose_1", "doorClose_2"]), pk("door")], {}),
    "ding": (1.0, "ding", [K(KI, ["confirmation_001", "confirmation_002", "confirmation_003", "bong_001"]), pk("ding")], {}),
    "coins": (.8, "coins", [K(KR, ["handleCoins", "handleCoins2"]), pk("coins", 2)], {}),
    "footstep": (.4, "footstep", [K(KM, [f"footstep_wood_00{i}" for i in range(5)]), pk("footstep")], {}),
}
SEED = int(os.environ.get("REEL_SEED", "0") or 0)
OK_LIC = ("cc0", "public domain")
BAD_TITLE = re.compile(r"^File:(LL-|[A-Z][a-z]{1,3}(-[a-z]{2,3})?-)")  # word-pronunciation recordings


def get(url, timeout=25):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def freesound(q, tgt):
    tok = os.environ.get("FREESOUND_TOKEN")
    if not tok: return None
    u = "https://freesound.org/apiv2/search/text/?" + urllib.parse.urlencode(dict(
        query=q, filter=f'license:"Creative Commons 0" duration:[0.05 TO {max(tgt * 4, 2)}]', sort="rating_desc",
        fields="id,name,previews,username,duration", page_size=5, token=tok))
    r = json.loads(get(u))["results"]
    if not r: return None
    x = r[0]
    return x["previews"]["preview-hq-mp3"], f"Freesound #{x['id']} '{x['name']}' by {x['username']} (CC0)"


def wikimedia(q, tgt):
    u = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(dict(
        action="query", format="json", generator="search", gsrnamespace=6, gsrlimit=50,
        gsrsearch=f"{q} filetype:audio", prop="imageinfo", iiprop="url|extmetadata",
        iiextmetadatafilter="LicenseShortName"))
    best = None
    for p in json.loads(get(u)).get("query", {}).get("pages", {}).values():
        ii = p["imageinfo"][0]
        lic = ii["extmetadata"].get("LicenseShortName", {}).get("value", "").lower()
        d = ii.get("duration") or 0
        if BAD_TITLE.match(p["title"]) or not any(k in lic for k in OK_LIC) or not (0.08 < d < max(6, tgt * 6)):
            continue
        sc = abs(np.log(d / tgt)) - 0.4 * sum(w in p["title"].lower() for w in q.lower().split())
        if best is None or sc < best[0]:
            best = (sc, ii["url"], f"Wikimedia Commons {p['title']} ({lic})")
    return best and best[1:]


def best_event(x, sr, tgt, win=False, pick=0):
    """Archive files hold many takes: pick one strong event near the target length (pick = variant index)."""
    hop = sr // 100
    e = np.sqrt(np.convolve(x ** 2, np.ones(hop) / hop, "same")[::hop])
    thr = max(e.max() * .08, 1e-4)
    on = e > thr
    segs, s = [], None
    for i, v in enumerate(on):
        if v and s is None: s = i
        if not v and s is not None:
            if i - s > 3: segs.append((s, i))
            s = None
    if s is not None: segs.append((s, len(on)))
    if not segs: return x[: int(tgt * sr)]
    if win:
        a = max(0, segs[min(pick, len(segs) - 1)][0] * hop - int(.01 * sr))
        return x[a:a + int(tgt * sr)].copy()
    rank = sorted(segs, key=lambda ab: -(e[ab[0]:ab[1]].max() - .15 * abs(np.log(max((ab[1] - ab[0]) / 100, .05) / tgt))))
    a, b = rank[min(pick, len(rank) - 1, 2)]
    a = max(0, a * hop - int(.01 * sr))
    b = min(len(x), max(b * hop, a + int(.08 * sr)), a + int(tgt * 1.6 * sr))
    return x[a:b].copy()


def finish(src, out, tgt, opt, pick):
    tmp = out + ".raw.wav"
    run(["-i", src, "-ac", "1", "-ar", "44100", "-c:a", "pcm_s16le", tmp])
    with wave.open(tmp) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    os.remove(tmp)
    if len(x) < 400 or np.abs(x).max() < 1e-3: return False
    y = best_event(x, 44100, tgt, opt.get("win"), pick)
    if opt.get("rev"): y = y[::-1].copy()  # reversed whoosh = riser into the hit
    n = min(len(y) // 3, int(.04 * 44100)); y[-n:] *= np.linspace(1, 0, n)
    m = min(len(y) // 4, int(.004 * 44100)); y[:m] *= np.linspace(0, 1, m)
    y = y / (np.abs(y).max() + 1e-9) * 10 ** (-3 / 20)
    with wave.open(out, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(44100)
        w.writeframes((y * 32767).astype(np.int16).tobytes())
    return True


def fetch(role, depth=0):
    d = wp("sfx"); os.makedirs(d, exist_ok=True)
    out = os.path.join(d, role + ".wav")
    if os.path.exists(out): return out
    tgt, q, srcs, opt = ROLES.get(role, (.6, role.replace("_", " "), [], {}))
    tries = []
    if os.environ.get("FREESOUND_TOKEN"): tries.append(lambda: freesound(q, tgt))
    for kind, urls, lic in srcs:
        i = SEED % len(urls)
        tries.append(lambda u=urls[i], lic=lic: (u, f"{lic}: {u.rsplit('/', 1)[-1]}"))
        if len(urls) > 1:
            tries.append(lambda u=urls[(i + 1) % len(urls)], lic=lic: (u, f"{lic}: {u.rsplit('/', 1)[-1]}"))
    tries.append(lambda: wikimedia(q, tgt))
    for fn in tries:
        try:
            hit = fn()
            if not hit: continue
            url, credit = hit
            raw = os.path.join(d, role + ".src")
            with open(raw, "wb") as f: f.write(get(url, 60))
            ok = finish(raw, out, tgt, opt, SEED % 3 if "archive.org" in url else 0)
            os.remove(raw)
            if ok:
                with open(os.path.join(d, "credits.txt"), "a") as f: f.write(f"{role}: {credit}\n")
                return out
        except Exception as e:
            sys.stderr.write(f"[{role}] {str(e)[:60]}\n")
            if "429" in str(e): time.sleep(2)
    if opt.get("alias") and depth == 0:
        a = fetch(opt["alias"], 1)
        if a:
            import shutil; shutil.copy(a, out); return out
    print(f"SFX_MISSING {role}")
    return None


if __name__ == "__main__":
    got = [r for r in sys.argv[1:] if fetch(r)]
    print("sfx ok:", " ".join(got))
