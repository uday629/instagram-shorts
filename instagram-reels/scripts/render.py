"""Edit + render: cut, color-correct, 9:16 reframe, punch-ins, captions, motion graphics, music, SFX, mix.
usage: render.py plan.json [--part i/n] [--out path]   (re-run to resume; parts let long renders fit tool time limits)"""
import os, sys, re, json, math, subprocess, wave, hashlib
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from lib import (W, H, FPS, wp, run, ffmpeg, jload, jsave, probe, clamp, ease_out_cubic, ease_out_expo, ease_in_out,
                 spring, h8)
import style as ST
import fonts as FT

STOP = set("a an the is are am was were be to of in on at and or but so it its this that i you we he she they my your "
           "our just really very like um uh ah er hmm okay ok yeah well then than do does did have has had for with as "
           "by from not no think thing things know get got going doing done because about also there there's here "
           "what where when who how why if some any all more much can could would should will me us them him her "
           "been being let lets let's say said go goes make made want see look way time right now actually basically".split())
SFX_GAIN = dict(whoosh=-18, whoosh_soft=-21, click=-17, tick=-19, tap=-18, pop=-17, impact=-12, impact_soft=-15,
                riser=-17, paper=-16, typewriter=-20, heartbeat=-15, stamp=-15, glitch=-20, boing=-17, scratch=-18,
                door=-18, ding=-19, coins=-16, keyboard=-19, camera=-17, footstep=-18, breath=-20, phone_buzz=-19, pencil=-17)


# ------------------------------------------------------------------ timeline
def segments(plan, A):
    dur = A["probe"]["dur"]
    if plan.get("cut", "auto") == "none" or (plan.get("cut", "auto") == "auto" and not A["needs_cut"]):
        segs = [[0.0, dur]]
    else:
        segs = [[max(0, s - .08), min(dur, e + .14)] for s, e in A["speech"]]
        mg = []
        for s, e in segs:
            if mg and s - mg[-1][1] < .28: mg[-1][1] = e
            else: mg.append([s, e])
        segs = mg
    rem = plan.get("remove", [])
    if rem == "auto": rem = [b[:2] for b in A.get("bad_takes", [])]
    for r0, r1 in rem:
        out = []
        for s, e in segs:
            if e <= r0 or s >= r1: out.append([s, e]); continue
            if s < r0: out.append([s, r0])
            if e > r1: out.append([r1, e])
        segs = out
    if plan.get("trim"):
        a, b = plan["trim"]
        segs = [[max(s, a), min(e, b)] for s, e in segs if e > a and s < b]
    return [[round(s, 3), round(e, 3)] for s, e in segs if e - s >= 4 / FPS]  # no flash frames


class TL:
    def __init__(s, segs):
        s.segs = segs; s.off = []
        t = 0
        for a, b in segs: s.off.append(t); t += b - a
        s.dur = t
        s.cuts = s.off[1:]

    def o(s, t):  # source -> output time (None if removed)
        for (a, b), o in zip(s.segs, s.off):
            if a - 1e-3 <= t <= b + 1e-3: return o + t - a
        return None

    def near(s, t):  # map even if inside removed part (snap forward)
        v = s.o(t)
        if v is not None: return v
        for (a, b), o in zip(s.segs, s.off):
            if a > t: return o
        return s.dur

    def seg_at(s, to):
        i = 0
        for k, o in enumerate(s.off):
            if to >= o - 1e-6: i = k
        return i


# ------------------------------------------------------------------ prep: cut + grade + reframe + voice
def make_lut(A, tint, force):
    c = A["color"]
    need = c["needs_grade"] or force == "force"
    g = np.linspace(0, 1, 33, dtype=np.float32)
    b_, g_, r_ = np.meshgrid(g, g, g, indexing="ij")
    x = np.stack([r_, g_, b_], -1)
    if need:
        cr, cb = c["cast_rb"]
        gain = np.array([1 - cr * .9, 1.0, 1 - cb * .9], np.float32)
        x = x * gain
        bi, wi = max(0, c["black"] - .005), min(1, max(c["white"] + .01, .6))
        x = (x - bi) / (wi - bi)
        x = .02 + np.clip(x, 0, 1.05) * .93
        k = .16 if c["ystd"] < .18 else .1
        sat = clamp(.33 / max(c["sat"], .05), .92, 1.25)
    else:
        k, sat = .04, 1.0
    if tint == "contrast": k += .06
    Y = (x * [.2126, .7152, .0722]).sum(-1, keepdims=True)
    Ys = Y + k * (Y - .45) * (1 - np.abs(2 * Y - .9)).clip(0)
    x = x + (Ys - Y)
    Y = (x * [.2126, .7152, .0722]).sum(-1, keepdims=True)
    skin = ((x[..., :1] > x[..., 1:2]) & (x[..., 1:2] > x[..., 2:3])).astype(np.float32)  # warm hues: protect
    s = sat * (1 - .4 * skin * (sat > 1)) + (1 - (1 - .4 * skin * (sat > 1))) * 1.0
    if tint == "sepia": s = s * .82
    x = Y + (x - Y) * s
    tw = .5 if not need else 1.0
    if tint in ("warm", "sepia"): x = x + tw * np.concatenate([.012 * Y, .004 * Y, -.012 * Y], -1)
    if tint == "cool": x = x + tw * np.concatenate([-.006 * (1 - Y), .0 * Y, .014 * (1 - Y)], -1)
    x = np.clip(x, 0, 1)
    p = wp("grade.cube")
    with open(p, "w") as f:
        f.write("LUT_3D_SIZE 33\n")
        for v in x.reshape(-1, 3): f.write(f"{v[0]:.5f} {v[1]:.5f} {v[2]:.5f}\n")
    return p, need


def prep(plan, A, segs, tint):
    base, voice = wp("base.mp4"), wp("voice.wav")
    key = h8(json.dumps([segs, tint, plan.get("grade", "auto"), plan.get("look")]))
    if os.path.exists(base) and jload(wp("prep.json"), {}).get("key") == key: return
    raw, P = A["raw"], A["probe"]
    lut, graded = make_lut(A, tint, plan.get("grade", "auto"))
    face = A.get("face") or {"cx": .5}
    sw, sh = P["w"], P["h"]
    if sw / sh > W / H + .01:  # landscape/square -> crop around the face
        cw = sh * W / H
        x0 = clamp(face["cx"] * sw - cw / 2, 0, sw - cw)
        frame = f"crop={int(cw)//2*2}:{sh//2*2}:{int(x0)}:0,scale={W}:{H}:flags=lanczos"
    else:
        frame = f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H}"
    look = ""
    if plan.get("look") == "grain" or tint in ("sepia",): look = ",noise=alls=5:allf=t"
    if plan.get("vignette", tint in ("contrast", "sepia", "cool")): look += ",vignette=PI/5"
    fg, n = [], len(segs)
    for i, (s, e) in enumerate(segs):
        fg.append(f"[0:v]trim={s}:{e},setpts=PTS-STARTPTS[v{i}];")
        fd = min(.012, (e - s) / 4)
        fg.append(f"[0:a]atrim={s}:{e},asetpts=PTS-STARTPTS,afade=t=in:d={fd},afade=t=out:st={e - s - fd:.4f}:d={fd}[a{i}];")
    fg.append("".join(f"[v{i}][a{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[cv][ca];")
    fg.append(f"[cv]fps={FPS},{frame},lut3d='{lut}',format=yuv420p{look}[vo];")
    fg.append("[ca]aresample=48000,highpass=f=75,afftdn=nf=-28,acompressor=threshold=-21dB:ratio=3:attack=8:release=160,"
              "equalizer=f=3500:t=q:w=1.2:g=2[ao]")
    fs = wp("prep.fg"); open(fs, "w").write("".join(fg))
    run(["-i", raw, "-filter_complex_script", fs, "-map", "[vo]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "14",
         "-an", base, "-map", "[ao]", "-ac", "1", "-c:a", "pcm_s16le", voice])
    jsave(wp("prep.json"), dict(key=key, graded=graded))


# ------------------------------------------------------------------ text sprites (ffmpeg drawtext = HarfBuzz shaping, any script)
_SPR = {}


def sprite(text, font, size, color, shadow=True):
    k = (text, font, size, color, shadow)
    if k in _SPR: return _SPR[k]
    p = wp("spr", h8(repr(k)) + ".png")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    if not os.path.exists(p):
        tf = p + ".txt"; open(tf, "w", encoding="utf-8").write(text)
        cw, ch = int(len(text) * size * .75 + size * 2), int(size * 2.2)
        col = "0x%02x%02x%02x" % tuple(color)
        f = font.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
        t = tf.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
        run(["-f", "lavfi", "-i", f"color=c=black@0.0:s={cw}x{ch},format=rgba", "-frames:v", "1", "-vf",
             f"drawtext=fontfile='{f}':textfile='{t}':fontsize={size}:fontcolor={col}:x={int(size*.5)}:y={int(size*.4)}",
             p])
        os.remove(tf)
    im = Image.open(p).convert("RGBA")
    bb = im.getchannel("A").getbbox() or (0, 0, 1, 1)
    im = im.crop(bb)
    if shadow:
        pad = max(6, size // 7)
        sh = Image.new("RGBA", (im.width + pad * 2, im.height + pad * 2), (0, 0, 0, 0))
        a = Image.new("L", sh.size, 0); a.paste(im.getchannel("A"), (pad, pad + max(2, size // 28)))
        a = a.filter(ImageFilter.GaussianBlur(max(3, size // 14))).point(lambda v: int(v * .62))
        sh.putalpha(a)
        sh.alpha_composite(im, (pad, pad))
        im = sh
        im.info["pad"] = pad
    else:
        im.info["pad"] = 0
    _SPR[k] = im
    return im


def fit_size(text, font, size, maxw):
    s = size
    while s > 34:
        im = sprite(text, font, s, (255, 255, 255), False)
        if im.width <= maxw: return s
        s = int(s * .92)
    return s


# ------------------------------------------------------------------ captions
def auto_captions(tr, tl, emph):
    if not tr.get("ok"): return []
    words = [w for w in tr["words"] if tl.o(w[1]) is not None and w[0].strip()]
    groups, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        span = w[2] - cur[0][1]
        brk = (not nxt or nxt[1] - w[2] > .45 or (re.search(r"[.!?;:।]$", w[0]) and span > .7) or span > 1.9 or len(cur) >= 6)
        if brk: groups.append(cur); cur = []
    merged = []  # captions need >= ~1 s on screen; fold short groups into the next one
    for g in groups:
        if merged and merged[-1][-1][2] - merged[-1][0][1] < .9 and len(merged[-1]) + len(g) <= 7 and g[0][1] - merged[-1][-1][2] < .5:
            merged[-1] = merged[-1] + g
        else:
            merged.append(g)
    groups = merged
    caps = []
    for g in groups:
        toks = [re.sub(r"^[^\w]+|[^\w%$৳₹]+$", "", w[0]) for w in g]
        if not any(toks): continue
        cand = [(i, t) for i, t in enumerate(toks) if t and t.lower() not in STOP]
        if not cand: continue
        num = [c for c in cand if re.search(r"\d", c[1])]
        em = [c for c in cand if c[1].lower() in emph]
        ki = (num or em or [max(cand, key=lambda c: len(c[1]))])[0][0]
        keep = [t for t in toks[:ki] if t and t.lower() not in ("um", "uh", "like", "so", "and", "but")]
        lead = " ".join(keep[-4:]) if ki > 0 else ""  # lead = context before the key, max 4 words
        caps.append(dict(t=[g[0][1], g[-1][2]], kt=g[ki][1], key=toks[ki], lead=lead if len(lead) > 1 else "",
                         wt=[[toks[i], g[i][1]] for i in range(len(g)) if i != ki],
                         accent=bool(num or em)))
    return caps


class Caption:
    LAYOUTS = ["L", "R", "C", "I"]

    def __init__(s, c, idx, S, tl, face):
        s.c, s.S = c, S
        s.t0 = tl.near(c["t"][0]); s.t1 = tl.near(c["t"][1]) + .25
        s.kt = tl.near(c.get("kt", c["t"][0]))
        s.anim = c.get("anim") or S["anims"][idx % len(S["anims"])]
        s.layout = c.get("layout") or s.LAYOUTS[idx % 4]
        col = S["colors"]
        up = S["script"] == "latin" and s.anim == "slam"
        key = c["key"].upper() if up or c.get("caps") else c["key"]
        s.key, s.lead, s.acc = key, c.get("lead", ""), c.get("acc", "")
        hf = FT.get(S["head"][0], S["head"][1], False, S["sub"])
        lf = FT.get(S["lead"][0], S["lead"][1], S["lead"][2], S["sub"])
        base = int(c.get("size", 132 if S["script"] == "latin" else 112))
        maxw = int(W * .76)
        s.K = fit_size(key, hf, base, maxw)
        s.L = max(int(s.K / 1.618), 30)
        s.hl = c.get("hl", False)
        kc = col["hl_text"] if s.hl else (col["accent"] if c.get("accent") else col["text"])
        s.kim = sprite(key, hf, s.K, kc, not s.hl)
        s.lim = sprite(s.lead, lf, fit_size(s.lead, lf, s.L, maxw), col["text"]) if s.lead else None
        if s.lim and s.lim.width > s.kim.width * .98:  # lead must never be wider than the key
            k2 = fit_size(key, hf, min(int(s.K * 1.7), int(s.K * s.lim.width / max(s.kim.width, 1) * 1.08)), maxw)
            if k2 > s.K:
                s.K = k2; s.kim = sprite(key, hf, s.K, kc, not s.hl)
            if s.lim.width > s.kim.width * .98: s.layout = "I"
        s.aim = sprite(s.acc, lf, s.L, col["secondary"]) if s.acc else None
        s.words = []
        if s.anim == "word" and c.get("wt") and s.lead:
            s.words = [(sprite(w, lf, s.L, col["text"]), tl.near(t)) for w, t in c["wt"]]
        s.count = None
        m = re.fullmatch(r"([^\d]*)([\d,]+(?:\.\d+)?)([^\d]*)", key)
        if s.anim == "count" and m:
            s.count = (m[1], float(m[2].replace(",", "")), m[3], "." in m[2], hf, kc)
        elif s.anim == "count":
            s.anim = "pop"
        yc = c.get("y") or (.70 if face and face.get("framing") == "tight" else .655)
        s.layout_boxes(yc)

    def layout_boxes(s, yc):
        kw, kh = s.kim.size
        lw, lh = s.lim.size if s.lim else (0, 0)
        gap = int(s.K * .06)
        ky = int(H * yc - kh / 2)
        x_min, x_max = int(W * .06), int(W * .85)
        if s.layout == "I" and s.lim and lw + kw + s.K * .2 <= x_max - x_min:
            tot = lw + kw + int(s.K * .18)
            x0 = int((x_min + x_max) / 2 - tot / 2)
            s.kpos = (x0 + lw + int(s.K * .18), ky)
            s.lpos = (x0, ky + kh - lh - int(s.K * .08))
        else:
            if s.layout == "I": s.layout = "C"
            if s.layout == "L": kx = x_min
            elif s.layout == "R": kx = x_max - kw
            else: kx = int((x_min + x_max) / 2 - kw / 2)
            s.kpos = (kx, ky)
            if s.lim:
                if s.layout == "L": lx = kx + int(min(kw * .12, max(0, kw - lw)))
                elif s.layout == "R": lx = kx + max(0, kw - lw - int(kw * .12))
                else: lx = kx + (kw - lw) // 2
                s.lpos = (int(clamp(lx, x_min, x_max - lw)), ky - lh + gap)
        if s.aim:
            aw, ah = s.aim.size
            ax = s.kpos[0] + kw - aw if s.layout != "R" else s.kpos[0]
            s.apos = (int(clamp(ax, x_min, x_max - aw)), s.kpos[1] + kh - gap)
        top = min([s.kpos[1]] + ([s.lpos[1]] if s.lim else []))
        if top < H * .12:  # keep out of the top dead zone
            dy = int(H * .12 - top); s.kpos = (s.kpos[0], s.kpos[1] + dy)
            if s.lim: s.lpos = (s.lpos[0], s.lpos[1] + dy)
            if s.aim: s.apos = (s.apos[0], s.apos[1] + dy)

    def bbox(s):
        bs = [(s.kpos, s.kim.size)] + ([(s.lpos, s.lim.size)] if s.lim else []) + ([(s.apos, s.aim.size)] if s.aim else [])
        return [min(p[0] for p, _ in bs), min(p[1] for p, _ in bs), max(p[0] + z[0] for p, z in bs), max(p[1] + z[1] for p, z in bs)]

    def scrim_for(s, fr):
        """Measure what is really behind the lockup; add a soft dark scrim only when text would not read."""
        x0, y0, x1, y1 = [int(v) for v in s.bbox()]
        reg = np.asarray(fr.crop((max(0, x0), max(0, y0), min(W, x1), min(H, y1))).convert("L"), np.float32) / 255
        busy = float(reg.std()) if reg.size else 0
        dark_text = sum(s.S["colors"]["text"]) < 384
        if reg.size == 0 or s.hl: return None
        if not dark_text and reg.mean() < .42 and busy < .22: return None
        if dark_text and reg.mean() > .58 and busy < .22: return None
        m = int(s.K * .6)
        im = Image.new("L", (x1 - x0 + 2 * m, y1 - y0 + 2 * m), 0)
        ImageDraw.Draw(im).rounded_rectangle([m // 2, m // 2, im.width - m // 2, im.height - m // 2], radius=m, fill=int(255 * .55))
        im = im.filter(ImageFilter.GaussianBlur(m // 2))
        sc = Image.new("RGBA", im.size, s.S["colors"]["neutral"] + (0,) if dark_text else (8, 8, 10, 0)); sc.putalpha(im)
        return sc, (x0 - m, y0 - m)

    def draw(s, fr, t, shake):
        if not (s.t0 - .02 <= t <= s.t1): return
        if not hasattr(s, "scrim"): s.scrim = s.scrim_for(fr)
        out = clamp((s.t1 - t) / .14)
        if s.scrim: paste(fr, s.scrim[0], s.scrim[1], clamp((t - s.t0) / .2) * out)
        lt = t - s.t0
        kstart = clamp(s.kt - .04, s.t0, max(s.t0, s.t1 - .55))
        kt = t - kstart
        if s.lim:
            if s.words:
                x = s.lpos[0]
                for im, wt in s.words:
                    p = clamp((t - wt + .02) / .18)
                    if p > 0: paste(fr, im, (x, s.lpos[1] + int(10 * (1 - ease_out_cubic(p)))), p * out)
                    x += im.width - 2 * im.info["pad"] + int(s.L * .28)
            else:
                p = ease_out_cubic(lt / .3)
                paste(fr, s.lim, (s.lpos[0], s.lpos[1] + int(14 * (1 - p))), clamp(lt / .2) * out)
        if kt < 0: return
        im, (x, y) = s.kim, s.kpos
        a, sc, blur, crop = clamp(kt / .12), 1.0, 0, None
        if s.anim == "pop": sc = .55 + .45 * spring(kt / .45)
        elif s.anim == "slam":
            sc = 1.45 - .45 * ease_out_expo(kt / .2); a = clamp(kt / .05)
            if kt < .3: shake[0] = 7 * (1 - kt / .3)
        elif s.anim == "rise":
            p = ease_out_cubic(kt / .32); crop = ("rise", p)
        elif s.anim == "blur":
            p = ease_out_cubic(kt / .38); blur = 16 * (1 - p); sc = 1.05 - .05 * p; a = clamp(kt / .3)
        elif s.anim == "type":
            crop = ("type", clamp(kt / min(.55, .045 * len(s.key) + .1)))
        elif s.anim == "word":
            sc = .8 + .2 * ease_out_cubic(kt / .25)
        if s.count:
            pre, v, suf, dec, hf, kc = s.count
            p = ease_out_expo(kt / .7)
            val = v * p
            txt = f"{pre}{val:,.1f}{suf}" if dec else f"{pre}{int(round(val)):,}{suf}"
            im = sprite(txt, hf, s.K, kc)
            x = s.kpos[0] + (s.kim.width - im.width) // 2 if s.layout == "C" else (s.kpos[0] + s.kim.width - im.width if s.layout == "R" else x)
        if s.hl:
            p = ease_in_out(kt / .28)
            pad = im.info["pad"] if "pad" in im.info else 0
            bw = int((im.width + s.K * .25) * p)
            if bw > 2:
                d = ImageDraw.Draw(fr, "RGBA")
                x0 = x - int(s.K * .12); y0 = y - int(s.K * .1); y1 = y + im.height + int(s.K * .1)
                d.rounded_rectangle([x0, y0, x0 + bw, y1], radius=int(s.K * .1), fill=s.S["colors"]["accent"] + (235,))
        if crop:
            kind, p = crop
            w, h = im.size
            if kind == "type":
                cw = max(1, int(w * p)); im = im.crop((0, 0, cw, h))
                if p < 1 and int(t * 4) % 2 == 0:
                    ImageDraw.Draw(fr).rectangle([x + cw, y + h * .15, x + cw + max(3, s.K // 22), y + h * .85], fill=s.S["colors"]["accent"])
            else:
                vis = max(1, int(h * p)); im = im.crop((0, 0, w, vis)); y = y + (h - vis)
        if blur > .5: im = im.filter(ImageFilter.GaussianBlur(blur))
        if abs(sc - 1) > .005:
            w, h = im.size
            im = im.resize((max(1, int(w * sc)), max(1, int(h * sc))), Image.BILINEAR)
            x, y = x - (im.width - w) // 2, y - (im.height - h) // 2
        paste(fr, im, (x, y), a * out)
        if s.c.get("ul"):
            p = ease_out_cubic((kt - .15) / .35)
            if p > 0:
                seed = int(t * 12)
                r = np.random.default_rng(seed)
                x0, y0 = s.kpos[0] + 8, s.kpos[1] + s.kim.height - 6
                L = (s.kim.width - 16) * p
                pts = [(x0 + L * i / 20, y0 + 5 * math.sin(i * .9) + r.uniform(-1.5, 1.5)) for i in range(21)]
                ImageDraw.Draw(fr).line(pts, fill=s.S["colors"]["accent"], width=max(5, s.K // 16), joint="curve")
        if s.aim and kt > .12:
            paste(fr, s.aim, s.apos, clamp((kt - .12) / .2) * out)


def paste(fr, im, pos, a=1.0):
    if a <= .01: return
    if a < .99:
        im = im.copy(); im.putalpha(im.getchannel("A").point(lambda v: int(v * a)))
    fr.paste(im, (int(pos[0]), int(pos[1])), im)


# ------------------------------------------------------------------ motion graphics
class MG:
    def __init__(s, m, S, tl):
        s.m, s.S = m, S
        s.t0, s.t1 = tl.near(m["t"][0]), tl.near(m["t"][1])
        s.type = m["type"]
        col = S["colors"]
        hf = FT.get(S["head"][0], S["head"][1], False, S["sub"])
        lf = FT.get(S["lead"][0], S["lead"][1], S["lead"][2], S["sub"])
        bf = FT.get(S["body"][0], 500, False, S["sub"])
        if s.type == "card":
            s.a = sprite(m.get("title", ""), hf, fit_size(m.get("title", ""), hf, 84, int(W * .7)), col["primary"], False)
            s.b = sprite(m["sub"], lf, 46, col["primary"], False) if m.get("sub") else None
        elif s.type == "vs":
            s.a = sprite(m["a"], hf, fit_size(m["a"], hf, 120, int(W * .74)), col["text"])
            s.b = sprite(m["b"], hf, fit_size(m["b"], hf, 120, int(W * .74)), col["accent"])
            s.v = sprite(m.get("mid", "vs"), lf, 56, col["text"])
        elif s.type == "lower":
            s.a = sprite(m.get("title", ""), hf, 58, col["text"], False)
            s.b = sprite(m["sub"], bf, 38, col["neutral"], False) if m.get("sub") else None
        elif s.type == "quote":
            s.lines = [sprite(l, lf, fit_size(l, lf, 70, int(W * .7)), col["text"]) for l in m["text"].split("\n")]
            s.q = sprite("“", lf, 160, col["accent"])

    def active(s, t):
        return s.t0 <= t <= s.t1

    def draw(s, fr, t):
        if not s.active(t): return
        k = t - s.t0
        p = ease_out_cubic(k / .35); out = clamp((s.t1 - t) / .18)
        col = s.S["colors"]
        d = ImageDraw.Draw(fr, "RGBA")
        if s.type == "card":
            bw = max(s.a.width, s.b.width if s.b else 0) + 110
            bh = s.a.height + (s.b.height + 18 if s.b else 0) + 80
            x0, y0 = (W - bw) // 2 - 40, int(H * .14) - int(30 * (1 - p))
            d.rounded_rectangle([x0, y0, x0 + bw, y0 + bh], radius=34, fill=col["neutral"] + (int(242 * p * out),))
            d.rectangle([x0 + 34, y0 + bh - 16, x0 + 34 + int((bw - 68) * ease_in_out((k - .2) / .5)), y0 + bh - 10], fill=col["accent"] + (int(255 * out),))
            paste(fr, s.a, (x0 + 55, y0 + 38), p * out)
            if s.b: paste(fr, s.b, (x0 + 55, y0 + 38 + s.a.height + 18), clamp((k - .15) / .3) * out)
        elif s.type == "vs":
            cy = int(H * .62)
            pa, pb = ease_out_cubic(k / .3), ease_out_cubic((k - .35) / .3)
            paste(fr, s.a, ((W - s.a.width) // 2 - int(60 * (1 - pa)), cy - s.a.height - 34), pa * out)
            lw = int(W * .5 * ease_in_out((k - .2) / .3))
            if lw > 2: d.rectangle([W // 2 - lw // 2, cy - 3, W // 2 + lw // 2, cy + 3], fill=col["accent"] + (int(255 * out),))
            if k > .25: paste(fr, s.v, ((W - s.v.width) // 2, cy - s.v.height // 2), clamp((k - .25) / .2) * out)
            if pb > 0: paste(fr, s.b, ((W - s.b.width) // 2 + int(60 * (1 - pb)), cy + 34), pb * out)
        elif s.type == "lower":
            y = int(H * .72); x = int(W * .07)
            bw = int((max(s.a.width, s.b.width if s.b else 0) + 60) * ease_out_expo(k / .25))
            d.rectangle([x, y, x + 10, y + s.a.height + (s.b.height + 10 if s.b else 0) + 24], fill=col["accent"] + (int(255 * out),))
            d.rectangle([x + 10, y, x + 10 + bw, y + s.a.height + 24], fill=col["primary"] + (int(225 * out),))
            if k > .15: paste(fr, s.a, (x + 34, y + 12), clamp((k - .15) / .15) * out)
            if s.b and k > .3: paste(fr, s.b, (x + 34, y + s.a.height + 34), clamp((k - .3) / .2) * out)
        elif s.type == "quote":
            th = sum(i.height for i in s.lines) + 20 * len(s.lines)
            y = int(H * .60 - th / 2)
            paste(fr, s.q, (int(W * .1), y - s.q.height // 2 - 20), p * out)
            for i, im in enumerate(s.lines):
                pi = ease_out_cubic((k - .12 * i) / .4)
                paste(fr, im, ((W - im.width) // 2, y + int(16 * (1 - pi))), pi * out)
                y += im.height + 20


# ------------------------------------------------------------------ zoom plan
def zoom_fn(plan, A, tl, caps):
    face = A.get("face") or {}
    fr = face.get("framing", "medium")
    step = {"wide": 1.16, "medium": 1.09, "tight": 1.04}[fr]
    if plan.get("zoom") == "none": return lambda t: 1.0
    if A.get("edited"):  # keep the source's own shots; only gentle pushes that restart on its cuts
        step = 1.0
    gaps = [i for i in range(1, len(tl.segs)) if tl.segs[i][0] - tl.segs[i - 1][1] > .12]
    lvl, cur = [1.0], 1.0
    for i in range(1, len(tl.segs)):
        if i in gaps: cur = step if cur == 1.0 else 1.0
        lvl.append(cur)
    src = sorted(x for x in (tl.o(c) for c in A.get("src_cuts", [])) if x is not None)
    punches = [(c.kt, c.t1) for c in caps if c.c.get("punch")]
    for z in plan.get("punch", []): punches.append((tl.near(z[0]), tl.near(z[1])))

    def f(t):
        i = tl.seg_at(t)
        s, e = tl.off[i], tl.off[i] + (tl.segs[i][1] - tl.segs[i][0])
        for c in src:
            if s <= c <= t: s = c
        nxt = min([c for c in src if c > t] + [e])
        z = lvl[i] * (1 + .025 * clamp((t - s) / max(nxt - s, 1)))  # slow push inside each shot
        for a, b in punches:
            if a <= t <= b + .35:
                z *= 1 + .07 * ease_in_out((t - a) / .3) * (1 - ease_in_out((t - b) / .35))
        return z
    return f


# ------------------------------------------------------------------ audio
def auto_sfx(S, caps, mgs, tl):
    roles = set(S["sfx_roles"])
    ev, last = [], -9

    def add(t, r, force=False):
        nonlocal last
        if r not in roles and not force: return
        if t - last < 1.3 and not force: return
        ev.append([max(0, t), r]); last = t
    m = {"pop": ["pop", "tap", "click"], "slam": ["impact", "impact_soft"], "count": ["tick", "click"],
         "type": ["typewriter", "keyboard", "click"], "rise": ["whoosh_soft"], "blur": ["whoosh_soft"], "word": ["tap", "click"]}
    for i, c in enumerate(caps):
        opts = [r for r in m.get(c.anim, []) if r in roles]
        if opts and (c.anim in ("slam", "count", "type") or i % 3 == 0 or c.c.get("accent")):
            add(c.kt - (.08 if opts[0].startswith("whoosh") else .0), opts[0])
    for g in mgs:
        add(g.t0 - .05, "whoosh" if "whoosh" in roles else "whoosh_soft", True)
    if S["music"].get("lift") and "riser" in roles:
        ev.append([max(0, tl.near(S["music"]["lift"]) - 1.3), "riser"])
    return ev


def mix(S, tl, events, plan):
    import music as MU
    mus = wp("music.wav")
    M = S["music"]
    if plan.get("music_file"):
        run(["-i", plan["music_file"], "-t", f"{tl.dur + .5}", "-ac", "2", "-ar", "44100", mus])
    elif M["mood"] != "none":
        lift = tl.near(M["lift"]) if M.get("lift") is not None else None
        seed = int(h8(A_RAW[0])[:6], 16) % 997
        y = MU.compose(M["mood"], M["bpm"], tl.dur + .5, lift, seed)
        with wave.open(mus, "wb") as w:
            w.setnchannels(2); w.setsampwidth(2); w.setframerate(44100)
            w.writeframes((y.T * 32767).astype(np.int16).tobytes())
    import sfx as SX
    ins = ["-i", wp("voice.wav")]
    fg = ["[0:a]aresample=48000,asplit=2[vo][key];"]
    mixin = ["[vo]"]
    k = 1
    if os.path.exists(mus) and M["mood"] != "none":
        ins += ["-i", mus]
        fg.append(f"[1:a]aresample=48000,volume={M['gain']}dB[mu];[mu][key]sidechaincompress=threshold=0.025:ratio=8:attack=20:release=380[md];")
        mixin.append("[md]"); k = 2
    else:
        fg[0] = "[0:a]aresample=48000[vo];"
    cred = []
    for t, r in sorted(events):
        p = SX.fetch(r)
        if not p: continue
        ins += ["-i", p]
        ms = int(t * 1000)
        fg.append(f"[{k}:a]aresample=48000,adelay={ms}|{ms},volume={SFX_GAIN.get(r, -17)}dB[s{k}];")
        mixin.append(f"[s{k}]"); k += 1
    fg.append("".join(mixin) + f"amix=inputs={len(mixin)}:normalize=0:duration=first,alimiter=limit=0.89,"
              "loudnorm=I=-14:TP=-1.5:LRA=11[out]")
    fs = wp("mix.fg"); open(fs, "w").write("".join(fg))
    run(ins + ["-filter_complex_script", fs, "-map", "[out]", "-ar", "48000", "-c:a", "pcm_s16le", wp("final.wav")])


# ------------------------------------------------------------------ main
A_RAW = [""]


def main():
    args = sys.argv[1:]
    plan = jload(args[0]) or sys.exit("plan.json unreadable")
    part, parts = 0, 1
    out = plan.get("out") or ("/mnt/user-data/outputs/reel.mp4" if os.path.isdir("/mnt/user-data/outputs") else os.path.abspath("reel.mp4"))
    for i, a in enumerate(args):
        if a == "--part": part, parts = [int(x) for x in args[i + 1].split("/")]; part -= 1
        if a == "--out": out = args[i + 1]
    A = jload(wp("analysis.json")) or sys.exit("run analyze.py first")
    A_RAW[0] = A["raw"]
    os.environ.setdefault("REEL_SEED", str(int(h8(A["raw"])[:6], 16) % 97))
    tr = jload(wp("transcript.json"), {})
    segs = segments(plan, A)
    tl = TL(segs)
    sample = " ".join((c.get("key", "") + " " + c.get("lead", "")) for c in plan.get("captions", []) if isinstance(c, dict))
    if not sample and tr.get("ok"): sample = " ".join(w[0] for w in tr["words"][:30])
    S = ST.build(plan, A, sample)
    S["sub"] = S["script"]
    prep(plan, A, segs, S["tint"])
    capd = plan.get("captions", "auto")
    if capd == "auto": capd = auto_captions(tr, tl, set(x.lower() for x in plan.get("emphasis", [])))
    caps = []
    for i, c in enumerate(capd or []):
        cc = Caption(c, i, S, tl, A.get("face"))
        if cc.t1 - cc.t0 > .3: caps.append(cc)
    caps.sort(key=lambda c: c.t0)
    for a, b in zip(caps, caps[1:]):  # never overlap; outgoing caption finishes before the next starts
        a.t1 = min(a.t1, b.t0 - .03)
    mgs = [MG(m, S, tl) for m in plan.get("mg", [])]
    for g in mgs:  # MG owns the screen: hide captions under vs/quote/card
        if g.type in ("vs", "quote"):
            for c in caps:
                if c.t0 < g.t1 and c.t1 > g.t0: c.t1 = min(c.t1, g.t0 - .02) if c.t0 < g.t0 else c.t0 - 1
    caps = [c for c in caps if c.t1 - c.t0 > .3]
    jsave(wp("layout.json"), dict(dur=tl.dur, cuts=tl.cuts, caps=[dict(t=[round(c.t0, 2), round(c.t1, 2)], key=c.key, lead=c.lead,
                                                                       anim=c.anim, lay=c.layout, box=c.bbox()) for c in caps],
                                   mg=[dict(type=g.type, t=[round(g.t0, 2), round(g.t1, 2)]) for g in mgs], style=dict(
            ids=S["ids"], head=S["head"], lead=S["lead"], colors={k: "#%02x%02x%02x" % v for k, v in S["colors"].items()},
            music=S["music"], tint=S["tint"], log=S["log"])))
    zf = zoom_fn(plan, A, tl, caps)
    face = A.get("face") or {}
    ex, ey = (face.get("eye") or [.5, .35])
    P = A["probe"]
    if P["w"] / P["h"] > W / H + .01: ex = .5
    ex, ey = ex * W, ey * H
    brolls = []
    for b in plan.get("broll", []):
        brolls.append(dict(file=b["file"], t0=tl.near(b["t"][0]), t1=tl.near(b["t"][1])))
    nfr = int(round(tl.dur * FPS))
    a_, b_ = nfr * part // parts, nfr * (part + 1) // parts
    pfile = wp(f"part{part + 1}of{parts}.mp4")
    if not os.path.exists(pfile):
        dec = subprocess.Popen([ffmpeg(), "-v", "error", "-ss", f"{a_ / FPS:.4f}", "-i", wp("base.mp4"), "-frames:v", str(b_ - a_),
                                "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
        enc = subprocess.Popen([ffmpeg(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
                                "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
                                pfile + ".tmp.mp4"], stdin=subprocess.PIPE)
        bdec = {}
        for n in range(a_, b_):
            buf = dec.stdout.read(W * H * 3)
            if len(buf) < W * H * 3: break
            t = n / FPS
            fr = Image.frombuffer("RGB", (W, H), buf, "raw", "RGB", 0, 1)
            for b in brolls:
                if b["t0"] <= t <= b["t1"]:
                    if b["file"] not in bdec:
                        bdec[b["file"]] = subprocess.Popen([ffmpeg(), "-v", "error", "-ss", "0", "-i", b["file"], "-vf",
                                                            f"fps={FPS},scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}",
                                                            "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
                    bb = bdec[b["file"]].stdout.read(W * H * 3)
                    if len(bb) == W * H * 3:
                        bi = Image.frombuffer("RGB", (W, H), bb, "raw", "RGB", 0, 1)
                        z = 1 + .06 * (t - b["t0"]) / max(b["t1"] - b["t0"], .1)
                        bi = bi.resize((int(W * z), int(H * z)), Image.BILINEAR).crop(
                            (int(W * (z - 1) / 2), int(H * (z - 1) / 2), int(W * (z - 1) / 2) + W, int(H * (z - 1) / 2) + H))
                        al = clamp((t - b["t0"]) / .13) * clamp((b["t1"] - t) / .13)
                        fr = Image.blend(fr, bi, al) if al < 1 else bi
            z = zf(t)
            shake = [0.0]
            if abs(z - 1) > .002:
                cw, ch = W / z, H / z
                x0, y0 = ex * (1 - 1 / z), ey * (1 - 1 / z)
                fr = fr.resize((W, H), Image.BILINEAR, box=(x0, y0, x0 + cw, y0 + ch))
            else:
                fr = fr.copy()
            for c in caps: c.draw(fr, t, shake)
            for g in mgs: g.draw(fr, t)
            if shake[0] > .5:
                dx, dy = int(shake[0] * math.sin(t * 90)), int(shake[0] * math.cos(t * 70))
                fr = fr.transform((W, H), Image.AFFINE, (1, 0, -dx, 0, 1, -dy), Image.BILINEAR).resize((W, H))
                fr = fr.resize((int(W * 1.012), int(H * 1.012)), Image.BILINEAR).crop((6, 11, 6 + W, 11 + H))
            enc.stdin.write(fr.tobytes())
        enc.stdin.close(); enc.wait(); dec.wait()
        for p in bdec.values(): p.kill()
        os.replace(pfile + ".tmp.mp4", pfile)
    done = [wp(f"part{i}of{parts}.mp4") for i in range(1, parts + 1)]
    if not all(os.path.exists(p) for p in done):
        print(f"part {part + 1}/{parts} done; run the next part"); return
    events = auto_sfx(S, caps, mgs, tl) if plan.get("sfx", "auto") == "auto" else []
    for e in plan.get("sfx_add", []): events.append([tl.near(e[0]), e[1]])
    mix(S, tl, events, plan)
    lst = wp("parts.txt"); open(lst, "w").write("".join(f"file '{p}'\n" for p in done))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    run(["-f", "concat", "-safe", "0", "-i", lst, "-i", wp("final.wav"), "-map", "0:v", "-map", "1:a", "-c:v", "copy",
         "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out])
    cr = wp("sfx", "credits.txt")
    print(f"OUT {out} | {tl.dur:.1f}s | captions {len(caps)} | mg {len(mgs)} | sfx {len(events)} | music {S['music']['mood']}"
          + (f" | sfx credits: {cr}" if os.path.exists(cr) else ""))


if __name__ == "__main__":
    main()
