"""Google Fonts (OFL) on demand. Chain: Fontsource static TTF via jsDelivr -> google/fonts GitHub variable TTF
(instanced to the weight with fontTools). usage: fonts.py "Family" weight [italic] [latin|bengali|devanagari|arabic]"""
import os, sys, urllib.request
from lib import wp

UA = {"User-Agent": "instagram-reels-skill/1.0"}
SCRIPT_FONTS = {  # headline, body/lead, contrast-serif for non-Latin captions
    "bengali": [("Anek Bangla", 800), ("Hind Siliguri", 400), ("Noto Serif Bengali", 500)],
    "devanagari": [("Mukta", 800), ("Hind", 400), ("Noto Serif Devanagari", 500)],
    "arabic": [("Cairo", 800), ("Noto Sans Arabic", 400), ("Amiri", 400)],
}


def _get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return r.read()


def get(family, weight=400, italic=False, subset="latin"):
    d = wp("fonts"); os.makedirs(d, exist_ok=True)
    fid = family.lower().replace(" ", "-")
    style = "italic" if italic else "normal"
    out = os.path.join(d, f"{fid}-{subset}-{weight}-{style}.ttf")
    if os.path.exists(out): return out
    for w in [weight] + sorted({400, 500, 600, 700, 800, 900, 300} - {weight}, key=lambda x: abs(x - weight)):
        for st in ([style, "normal"] if italic else [style]):
            try:
                data = _get(f"https://cdn.jsdelivr.net/fontsource/fonts/{fid}@latest/{subset}-{w}-{st}.ttf")
                if len(data) > 5000:
                    open(out, "wb").write(data); return out
            except Exception:
                pass
    # fallback: variable font from github.com/google/fonts, instanced with fontTools
    cam = family.replace(" ", "")
    for lic in ("ofl", "apache", "ufl"):
        for fn in ([f"{cam}-Italic[wght].ttf"] if italic else []) + [f"{cam}[wght].ttf", f"{cam}[wdth,wght].ttf",
                                                                      f"{cam}[opsz,wght].ttf", f"{cam}-Regular.ttf"]:
            try:
                data = _get(f"https://raw.githubusercontent.com/google/fonts/main/{lic}/{cam.lower()}/" +
                            fn.replace("[", "%5B").replace("]", "%5D").replace(",", "%2C"))
            except Exception:
                continue
            tmp = out + ".var"; open(tmp, "wb").write(data)
            try:
                from fontTools.ttLib import TTFont
                from fontTools.varLib.instancer import instantiateVariableFont
                f = TTFont(tmp)
                if "fvar" in f:
                    ax = {a.axisTag: a for a in f["fvar"].axes}
                    loc = {t: (max(ax[t].minValue, min(ax[t].maxValue, weight)) if t == "wght" else ax[t].defaultValue) for t in ax}
                    f = instantiateVariableFont(f, loc)
                f.save(out); os.remove(tmp); return out
            except Exception:
                os.replace(tmp, out); return out
    fb = "Noto Sans" if subset == "latin" else SCRIPT_FONTS.get(subset, [None, ("Noto Sans", 400)])[1][0]
    if family != fb:
        return get(fb, weight, False, subset)
    import glob  # offline: any installed font beats failing
    for pat in ("/usr/share/fonts/**/DejaVuSans-Bold.ttf", "/usr/share/fonts/**/*.ttf", "/System/Library/Fonts/*.ttc",
                "/Library/Fonts/*.ttf", "C:/Windows/Fonts/arial.ttf"):
        hit = glob.glob(pat, recursive=True)
        if hit:
            print(f"FONT_FALLBACK {family} -> {hit[0]}"); return hit[0]
    raise SystemExit(f"FONT_MISSING {family}")


if __name__ == "__main__":
    a = sys.argv[1:]
    print(get(a[0], int(a[1]) if len(a) > 1 else 400, len(a) > 2 and a[2] == "italic", a[3] if len(a) > 3 else "latin"))
