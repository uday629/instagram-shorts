"""Turn niche row(s) + analysis + plan into a concrete style (colors adapted to the footage, fonts, motion, sound).
usage: style.py ID [ID2]   -> prints the merged sheet row(s) compactly (for the model to read)"""
import sys, os
from lib import DATA, jload, hex2rgb, ensure_contrast, contrast, lum

NICHES = jload(os.path.join(DATA, "niches.json"))
MOTION = jload(os.path.join(DATA, "motion.json"))


def row(i):
    return next(r for r in NICHES if r["id"] == int(i))


def detect_script(text):
    for ch in text:
        o = ord(ch)
        if 0x0980 <= o <= 0x09FF: return "bengali"
        if 0x0900 <= o <= 0x097F: return "devanagari"
        if 0x0600 <= o <= 0x06FF: return "arabic"
    return "latin"


def build(plan, A, sample_text=""):
    ids = plan.get("niche") or [13]
    ids = ids if isinstance(ids, list) else [ids]
    R = row(ids[0])
    R2 = row(ids[1]) if len(ids) > 1 else R
    pal = {k: hex2rgb(v) for k, v in R["palette"].items()}
    pal.update({k: hex2rgb(v) for k, v in (plan.get("palette") or {}).items()})  # brand override
    zl = A.get("caption_zone_luma", .3)
    zone = (int(zl * 255),) * 3
    log = []
    if zl < .55:
        text = ensure_contrast(pal["neutral"], zone, 7.0)
        dark = pal["primary"]
    else:
        text = ensure_contrast(pal["primary"], zone, 7.0)
        dark = pal["neutral"]
    acc = ensure_contrast(pal["accent"], zone, 3.5)
    if acc != pal["accent"]: log.append(f"accent {R['palette']['accent']} adjusted for contrast on footage")
    sec = ensure_contrast(pal["secondary"], zone, 3.0)
    hl_text = ensure_contrast(pal["primary"], acc, 4.5)
    script = detect_script(sample_text)
    f = R["fonts"]
    head = f["h"]
    lead = f.get("x") if f.get("x") and f["x"][2] else f["b"]  # prefer the row's italic face for leads
    if script != "latin":
        from fonts import SCRIPT_FONTS
        sf = SCRIPT_FONTS[script]
        head, lead = [sf[0][0], sf[0][1], False], [sf[2][0], sf[2][1], False]
    pr = R["preset"]
    m = plan.get("music") or {}
    return dict(
        ids=ids, script=script, log=log,
        colors=dict(text=text, accent=acc, secondary=sec, primary=pal["primary"], neutral=pal["neutral"], dark=dark, hl_text=hl_text),
        head=head, lead=lead, body=f["b"],
        anims=plan.get("anims") or pr["anims"], motion=MOTION[pr["motion_style"] - 1]["name"],
        sfx_roles=sorted(set(pr["sfx_roles"] + R2["preset"]["sfx_roles"][:1])),
        music=dict(mood=m.get("mood", pr["music_mood"]), bpm=m.get("bpm", pr["bpm"]), gain=m.get("gain", -24), lift=m.get("lift")),
        tint=plan.get("tint", pr["grade_tint"]),
        hook=R["hook"], notes=R["notes"])


def show(i):
    r = row(i)
    keys = ["niche", "broll", "mg_style", "elements", "motion", "palette_text", "music", "sfx", "delivery", "hook", "rhythm", "notes"]
    print(f"#{r['id']} " + " || ".join(f"{k}: {r[k]}" for k in keys))
    print(f"fonts {r['fonts']} | preset {r['preset']}")


if __name__ == "__main__":
    if len(sys.argv) == 1:
        print(" | ".join(f"{r['id']}:{r['niche']}" for r in NICHES))
    for i in sys.argv[1:]:
        show(i)
