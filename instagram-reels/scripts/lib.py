"""Shared helpers. Works on any Linux/macOS box with Python 3.9+, no GPU."""
import json, os, re, shutil, subprocess, sys, hashlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
WORK = os.path.abspath(os.environ.get("REEL_WORK", "work"))
W, H, FPS = 1080, 1920, 30
os.makedirs(WORK, exist_ok=True)


def wp(*a):
    return os.path.join(WORK, *a)


def _has_drawtext(exe):
    try:
        out = subprocess.run([exe, "-hide_banner", "-filters"], capture_output=True, text=True, timeout=20).stdout
        return " drawtext " in out and " lut3d " in out
    except Exception:
        return False


def ffmpeg():
    """Prefer a build with drawtext+harfbuzz (imageio-ffmpeg static), else system ffmpeg."""
    c = os.environ.get("REEL_FFMPEG")
    if c:
        return c
    cands = []
    try:
        import imageio_ffmpeg
        cands.append(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:
        pass
    if shutil.which("ffmpeg"):
        cands.append(shutil.which("ffmpeg"))
    for e in cands:
        if _has_drawtext(e):
            os.environ["REEL_FFMPEG"] = e
            return e
    if cands:
        os.environ["REEL_FFMPEG"] = cands[0]
        return cands[0]
    sys.exit("ffmpeg missing: run scripts/setup.sh")


def run(args, quiet=True, inp=None):
    cmd = [ffmpeg(), "-hide_banner", "-loglevel", "error", "-y"] + list(args)
    r = subprocess.run(cmd, capture_output=True, input=inp)
    if r.returncode != 0:
        sys.stderr.write((r.stderr or b"").decode(errors="ignore")[-1500:])
        raise SystemExit(f"ffmpeg failed: {' '.join(cmd[:12])}...")
    return r


def probe(path):
    """Duration, size (display-rotated), fps, has_audio — parsed from ffmpeg -i (no ffprobe needed)."""
    r = subprocess.run([ffmpeg(), "-hide_banner", "-i", path], capture_output=True, text=True)
    t = r.stderr
    d = re.search(r"Duration: (\d+):(\d+):([\d.]+)", t)
    dur = int(d[1]) * 3600 + int(d[2]) * 60 + float(d[3]) if d else 0.0
    v = re.search(r"Stream.*Video:.*?(\d{2,5})x(\d{2,5})", t)
    w, h = (int(v[1]), int(v[2])) if v else (0, 0)
    rot = re.search(r"rotation of (-?[\d.]+)", t) or re.search(r"rotate\s*:\s*(-?\d+)", t)
    if rot and abs(round(float(rot[1]))) % 180 == 90:
        w, h = h, w
    f = re.search(r"([\d.]+) fps", t)
    return dict(dur=dur, w=w, h=h, fps=float(f[1]) if f else 30.0, audio="Audio:" in t)


def jload(p, default=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def jsave(p, obj):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


def hex2rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def lum(rgb):
    def c(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * c(r) + 0.7152 * c(g) + 0.0722 * c(b)


def contrast(a, b):
    la, lb = sorted([lum(a), lum(b)], reverse=True)
    return (la + 0.05) / (lb + 0.05)


def shade(rgb, k):
    """k>0 lighten toward white, k<0 darken toward black."""
    return tuple(int(round(c + (255 - c) * k)) if k > 0 else int(round(c * (1 + k))) for c in rgb)


def ensure_contrast(fg, bg, target):
    """Move fg toward white or black (keeping hue) until WCAG contrast vs bg >= target; picks the shorter path."""
    if contrast(fg, bg) >= target:
        return fg
    best = None
    for sgn in (1, -1):
        k = 0.0
        while k < 1.0:
            k += 0.05
            c = shade(fg, sgn * k)
            if contrast(c, bg) >= target:
                if best is None or k < best[0]: best = (k, c)
                break
    if best: return best[1]
    return (255, 255, 255) if contrast((255, 255, 255), bg) > contrast((0, 0, 0), bg) else (0, 0, 0)


# ---- easing ----
def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def ease_out_cubic(t):
    t = clamp(t); return 1 - (1 - t) ** 3


def ease_out_expo(t):
    t = clamp(t); return 1.0 if t >= 1 else 1 - 2 ** (-10 * t)


def ease_in_out(t):
    t = clamp(t); return 3 * t * t - 2 * t * t * t


def ease_back(t, s=1.70158):
    t = clamp(t) - 1; return 1 + (s + 1) * t ** 3 + s * t ** 2


def spring(t, damp=7.0, freq=2.2):
    import math
    t = clamp(t)
    return 1 - math.exp(-damp * t) * math.cos(freq * 2 * math.pi * t)


def h8(s):
    return hashlib.md5(s.encode()).hexdigest()[:10]


def is_latin(text):
    return all(ord(c) < 0x250 or c in "’‘“”—–…•₹৳€£" for c in text)
