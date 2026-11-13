"""Study the raw clip: audio pauses, takes, transcript, color/grade need, framing, footage colors.
usage: analyze.py RAW [lang|auto]  -> work/analysis.json, work/sheet.jpg ; prints a compact summary"""
import sys, os, re, wave, difflib
import numpy as np
from PIL import Image, ImageDraw
from lib import wp, run, probe, jsave, jload


def vad(path):
    w = wave.open(path)
    a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    hop = 160  # 10 ms @16k
    n = len(a) // hop
    fr = a[: n * hop].reshape(n, hop)
    db = 20 * np.log10(np.sqrt((fr ** 2).mean(1)) + 1e-9)
    floor = np.percentile(db, 10)
    thr = max(floor + 14, np.percentile(db, 95) - 30, -45)
    sp = db > thr
    runs, s = [], None
    for i, v in enumerate(sp):
        if v and s is None: s = i
        if not v and s is not None: runs.append([s, i]); s = None
    if s is not None: runs.append([s, n])
    m = []
    for s, e in runs:
        if m and s - m[-1][1] < 15: m[-1][1] = e
        else: m.append([s, e])
    m = [[s / 100, e / 100] for s, e in m if e - s >= 8]
    return m, n / 100, float(thr)


def frames(raw, dur, k=6):
    out = []
    for i in range(k):
        t = dur * (0.08 + 0.84 * i / (k - 1))
        p = wp(f"f{i}.png")
        run(["-ss", f"{t:.2f}", "-i", raw, "-frames:v", "1", "-vf", "scale=540:-2", p])
        out.append((t, np.asarray(Image.open(p).convert("RGB"))))
    return out


def scene_cuts(raw):
    """Hard cuts already in the source (edited video / B-roll) via ffmpeg scene score on a small proxy."""
    import subprocess
    from lib import ffmpeg
    r = subprocess.run([ffmpeg(), "-hide_banner", "-i", raw, "-vf", "scale=160:-2,select='gt(scene,0.32)',showinfo",
                        "-an", "-f", "null", "-"], capture_output=True, text=True)
    return [round(float(x), 2) for x in re.findall(r"pts_time:([\d.]+)", r.stderr)]


def color_stats(imgs):
    x = np.concatenate([im.reshape(-1, 3) for im in imgs]).astype(np.float32) / 255
    Y = x @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    mx, mn = x.max(1), x.min(1)
    sat = np.where(mx > 0.15, (mx - mn) / (mx + 1e-6), 0)
    neu = (sat < 0.18) & (Y > 0.2) & (Y < 0.85)
    if neu.sum() > 500:
        g = x[neu].mean(0)
        cast = [float(g[0] - g[1]), float(g[2] - g[1])]
    else:
        g = x.mean(0)
        cast = [float((g[0] - g[1]) * 0.5), float((g[2] - g[1]) * 0.5)]
    st = dict(black=float(np.percentile(Y, 1)), white=float(np.percentile(Y, 99.5)), mid=float(np.median(Y)),
              ystd=float(Y.std()), sat=float(sat[mx > 0.15].mean()), cast_rb=[round(c, 3) for c in cast])
    st = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in st.items()}
    why = []
    if st["black"] > 0.07: why.append("lifted blacks")
    if st["white"] < 0.82: why.append("dull highlights")
    if max(abs(c) for c in cast) > 0.025: why.append("color cast")
    if st["sat"] < 0.2: why.append("low saturation")
    if st["ystd"] < 0.16: why.append("flat contrast")
    st["needs_grade"] = bool(why)
    st["why"] = why
    return st


def faces(imgs):
    import cv2
    cc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    res = []
    for im in imgs:
        g = cv2.cvtColor(im, cv2.COLOR_RGB2GRAY)
        f = cc.detectMultiScale(g, 1.1, 5, minSize=(40, 40))
        if len(f):
            x, y, w, h = max(f, key=lambda r: r[2] * r[3])
            H, W = g.shape
            res.append([(x + w / 2) / W, (y + h / 2) / H, w / W, h / H])
    if not res:
        return None
    r = np.median(np.array(res), 0)
    cx, cy, fw, fh = [round(float(v), 3) for v in r]
    return dict(cx=cx, cy=cy, fh=fh, eye=[cx, round(cy - fh * 0.1, 3)],
                framing="tight" if fh > 0.26 else "wide" if fh < 0.13 else "medium", boxes=res)


def palette(imgs, k=5):
    import cv2
    x = np.concatenate([im[::6, ::6].reshape(-1, 3) for im in imgs]).astype(np.float32)
    _, lab, cen = cv2.kmeans(x, k, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0), 2,
                             cv2.KMEANS_PP_CENTERS)
    cnt = np.bincount(lab.ravel(), minlength=k)
    return ["#%02x%02x%02x" % tuple(int(v) for v in cen[i]) for i in np.argsort(-cnt)]


def zone_luma(imgs):
    v = []
    for im in imgs:
        h, w, _ = im.shape
        z = im[int(h * .58):int(h * .78), int(w * .06):int(w * .85)].astype(np.float32) / 255
        v.append((z @ np.array([0.2126, 0.7152, 0.0722])).mean())
    return round(float(np.mean(v)), 3)


def norm(s):
    return re.sub(r"[^\w\s]", "", s.lower()).strip()


def bad_takes(lines):
    """A line whose text is (mostly) repeated by a later line within 20 s = a retake; drop the earlier one."""
    rm = []
    for i, (s, e, t) in enumerate(lines):
        a = norm(t)
        if len(a) < 6: continue
        for s2, e2, t2 in lines[i + 1:]:
            if s2 - e > 20: break
            b = norm(t2)[: len(a) + 10]
            if difflib.SequenceMatcher(None, a, b).ratio() > 0.62 or (len(a) > 12 and b.startswith(a[:12])):
                rm.append([s, round(s2 - 0.05, 2), t[:40]]); break
    return rm


def sheet(fr, face):
    tw, th = 240, 426
    S = Image.new("RGB", (tw * 3, th * 2), "black")
    d = ImageDraw.Draw(S)
    for i, (t, im) in enumerate(fr):
        x, y = (i % 3) * tw, (i // 3) * th
        S.paste(Image.fromarray(im).resize((tw, th)), (x, y))
        d.text((x + 6, y + 6), f"{t:.1f}s", fill="yellow")
    for z in (0.58, 0.80):  # caption zone guides
        for c in range(3):
            d.line([(c * tw, int(th * z)), ((c + 1) * tw, int(th * z))], fill=(0, 255, 0))
    S.save(wp("sheet.jpg"), quality=80)


def main():
    raw = os.path.abspath(sys.argv[1])
    lang = sys.argv[2] if len(sys.argv) > 2 else "auto"
    P = probe(raw)
    if not P["dur"]:
        sys.exit("cannot read video")
    run(["-i", raw, "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", wp("a16.wav")])
    speech, total, thr = vad(wp("a16.wav"))
    gaps = [[round(speech[i][1], 2), round(speech[i + 1][0], 2)] for i in range(len(speech) - 1)
            if speech[i + 1][0] - speech[i][1] > 0.45]
    head = speech[0][0] if speech else 0
    tail = total - speech[-1][1] if speech else 0
    fr = frames(raw, P["dur"])
    imgs = [f[1] for f in fr]
    face = faces(imgs)
    sheet(fr, face)
    col = color_stats(imgs)
    tr = jload(wp("transcript.json"), {})
    if tr.get("src") != raw or tr.get("req") != lang:  # cache: ASR is the slowest step
        sys.argv = ["asr", wp("a16.wav"), lang]
        import asr
        asr.main()
        tr = jload(wp("transcript.json"), {})
        tr.update(src=raw, req=lang); jsave(wp("transcript.json"), tr)
    bt = bad_takes(tr.get("lines", [])) if tr.get("ok") and tr.get("conf", -1) > -0.7 else []
    cuts = scene_cuts(raw)
    edited = len(cuts) / max(P["dur"] / 60, .25) > 5  # many hard cuts = already edited, keep its pacing
    sil = sum(e - s for s, e in gaps) + head + tail
    already_clean = edited or (len(gaps) <= 1 and head < 0.6 and tail < 0.8 and not bt)
    A = dict(raw=raw, probe=P, speech=[[round(s, 2), round(e, 2)] for s, e in speech], gaps=gaps,
             lead_in=round(head, 2), tail=round(tail, 2), silence_s=round(sil, 1), bad_takes=bt,
             needs_cut=not already_clean, edited=edited, src_cuts=cuts, color=col, face=face, palette=palette(imgs), caption_zone_luma=zone_luma(imgs),
             asr=bool(tr.get("ok")), lang=tr.get("lang"), asr_conf=tr.get("conf"))
    jsave(wp("analysis.json"), A)
    # compact summary for the model (keep it short = fewer tokens)
    print(f"dur {P['dur']:.1f}s {P['w']}x{P['h']} {P['fps']:.0f}fps | silence {sil:.1f}s gaps>{0.45}s:{len(gaps)} "
          f"| source cuts {len(cuts)}{' (ALREADY EDITED: keep pacing)' if edited else ''} | needs_cut {A['needs_cut']} | bad_takes {len(bt)}")
    print(f"grade {'NEEDED: ' + ', '.join(col['why']) if col['needs_grade'] else 'ok (already corrected)'} "
          f"| black {col['black']} white {col['white']} sat {col['sat']} cast {col['cast_rb']}")
    print(f"face {face and face['framing']} eye {face and face['eye']} | footage colors {' '.join(A['palette'])} "
          f"| caption-zone luma {A['caption_zone_luma']}")
    for b in bt:
        print(f"retake? {b[0]}-{b[1]} \"{b[2]}\"")
    if tr.get("ok"):
        bad = tr.get("conf", 0) < -0.85
        print(f"lang {tr['lang']} conf {tr.get('conf')}{' LOW -> text unreliable, timings ok' if bad else ''} | transcript:")
        for s, e, t in tr["lines"]:
            print(f"[{s:.1f}-{e:.1f}] {t}")
    else:
        print("transcript: NONE (ask user to paste script, or continue with audio-only cut)")


if __name__ == "__main__":
    main()
