"""Original royalty-free background music, synthesized from scratch (no samples, no copyright).
usage: music.py MOOD BPM DURATION_S OUT.wav [lift_s] [seed]
moods: warm_piano ambient drone cinematic pulse lofi groove marimba acoustic driving orchestral funk"""
import sys, hashlib
import numpy as np
from scipy.signal import butter, sosfilt, lfilter, sawtooth, fftconvolve

SR = 44100
rng = np.random.default_rng(0)
MAJ, MIN = [0, 2, 4, 5, 7, 9, 11], [0, 2, 3, 5, 7, 8, 10]
# progression = list of (scale degree, add7)
MOODS = {
    "warm_piano": dict(sc=MAJ, prog=[(0, 0), (4, 0), (5, 0), (3, 0)], inst=["piano_arp", "pad"], drums="shaker", rev=.3),
    "ambient": dict(sc=MAJ, prog=[(0, 1), (3, 1), (5, 1), (3, 1)], inst=["pad", "piano_sparse"], drums=None, rev=.4),
    "drone": dict(sc=MIN, prog=[(0, 0), (5, 0), (0, 0), (6, 0)], inst=["drone", "pad_dark", "piano_sparse"], drums="pulse", rev=.4),
    "cinematic": dict(sc=MIN, prog=[(0, 0), (5, 0), (2, 0), (6, 0)], inst=["strings", "ostinato"], drums="toms", rev=.35),
    "pulse": dict(sc=MIN, prog=[(0, 0), (5, 0), (2, 0), (6, 0)], inst=["arp16", "pad_dark", "bass8"], drums="four", rev=.25),
    "lofi": dict(sc=MAJ, prog=[(1, 1), (4, 1), (0, 1), (5, 1)], inst=["epiano", "bass_root"], drums="boombap", rev=.25, crackle=1),
    "groove": dict(sc=MIN, prog=[(0, 1), (5, 1), (2, 1), (6, 1)], inst=["pluck_chords", "bass8", "pad"], drums="four", rev=.22),
    "marimba": dict(sc=MAJ, prog=[(0, 0), (3, 0), (4, 0), (0, 0)], inst=["marimba_arp", "bass_root"], drums="shaker", rev=.22),
    "acoustic": dict(sc=MAJ, prog=[(0, 0), (4, 0), (5, 0), (3, 0)], inst=["strum", "bass_root"], drums="shaker", rev=.25),
    "driving": dict(sc=MIN, prog=[(0, 0), (5, 0), (6, 0), (4, 0)], inst=["stabs", "bass8", "pad_dark"], drums="rock", rev=.2),
    "orchestral": dict(sc=MIN, prog=[(0, 0), (3, 0), (5, 0), (4, 0)], inst=["strings", "ostinato", "piano_sparse"], drums="toms", rev=.4),
    "funk": dict(sc=MIN, prog=[(0, 1), (3, 1), (0, 1), (4, 1)], inst=["funk_bass", "clav"], drums="funk", rev=.15),
}


def hz(m): return 440.0 * 2 ** ((m - 69) / 12)
def tt(d): return np.arange(int(d * SR)) / SR
def lp(x, f, o=2): return sosfilt(butter(o, min(f, SR / 2 - 100), "low", fs=SR, output="sos"), x)
def hp(x, f, o=2): return sosfilt(butter(o, f, "high", fs=SR, output="sos"), x)
def bp(x, a, b): return sosfilt(butter(2, [a, b], "band", fs=SR, output="sos"), x)


def env(n, a=.005, r=.05):
    e = np.ones(n); na, nr = max(1, int(a * SR)), max(1, int(r * SR))
    e[:na] = np.linspace(0, 1, na); e[-nr:] *= np.linspace(1, 0, nr)
    return e


def piano(f, d, v=1.0):
    t = tt(d); x = np.zeros_like(t)
    for k in range(1, 9):
        fk = f * k * np.sqrt(1 + 0.0004 * k * k)
        if fk > 12000: break
        x += np.sin(2 * np.pi * fk * t) * np.exp(-t * (0.9 + 0.55 * k)) / k ** 1.3
    return v * x * env(len(t), .003, .08)


def epiano(f, d, v=1.0):
    t = tt(d); I = 1.4 * np.exp(-t * 3) + .15
    return v * np.sin(2 * np.pi * f * t + I * np.sin(2 * np.pi * f * t)) * np.exp(-t * 1.6) * env(len(t), .004, .1)


def pad(f, d, v=1.0, cut=1400, a=.6):
    t = tt(d)
    x = sum(sawtooth(2 * np.pi * f * (1 + dt) * t + rng.random() * 6) for dt in (-.004, 0, .005)) / 3
    return v * lp(x, cut) * env(len(t), a, min(.9, d / 2))


def strings(f, d, v=1.0):
    t = tt(d); vib = 1 + .003 * np.sin(2 * np.pi * 5.2 * t)
    x = sum(sawtooth(2 * np.pi * np.cumsum(f * (1 + dt) * vib) / SR) for dt in (-.006, .0, .007)) / 3
    return v * lp(x, 2200) * env(len(t), .35, min(.6, d / 2))


def pluck(f, d, v=1.0, bright=.5):
    n = int(d * SR); N = max(2, int(SR / f))
    x = np.zeros(n); x[:N] = lp(rng.uniform(-1, 1, N), 1500 + 6000 * bright)
    a = np.zeros(N + 2); a[0] = 1; a[N] = a[N + 1] = -0.497
    return v * lfilter([1], a, x) * env(n, .001, .05)


def marimba(f, d, v=1.0):
    t = tt(d)
    return v * (np.sin(2 * np.pi * f * t) * np.exp(-t * 5) + .25 * np.sin(2 * np.pi * 4 * f * t) * np.exp(-t * 22)
                + .08 * np.sin(2 * np.pi * 9.9 * f * t) * np.exp(-t * 45)) * env(len(t), .001, .05)


def bass(f, d, v=1.0):
    t = tt(d)
    return v * (np.sin(2 * np.pi * f * t) + .35 * lp(sawtooth(2 * np.pi * f * t), 500)) * env(len(t), .005, .06)


def noise(d): return rng.uniform(-1, 1, int(d * SR))


def kick(v=1.0):
    t = tt(.45); f = 45 + 80 * np.exp(-t * 28)
    return v * (np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 7) + .3 * lp(noise(.45), 3000) * np.exp(-t * 200))


def snare(v=1.0):
    t = tt(.3)
    return v * (.8 * bp(noise(.3), 1200, 6000) * np.exp(-t * 16) + .5 * np.sin(2 * np.pi * 185 * t) * np.exp(-t * 22))


def clap(v=1.0):
    t = tt(.3); x = bp(noise(.3), 900, 4000); e = np.zeros_like(t)
    for o in (0, .011, .023): e += (t >= o) * np.exp(-(t - o).clip(0) * 60)
    return v * x * e * .6


def hat(v=1.0, d=.08):
    t = tt(d); return v * hp(noise(d), 7000) * np.exp(-t * 45)


def shaker(v=1.0):
    t = tt(.12); return v * bp(noise(.12), 4500, 11000) * np.sin(np.pi * np.clip(t / .12, 0, 1)) ** 2


def tom(v=1.0):
    t = tt(.6); f = 80 + 70 * np.exp(-t * 12)
    return v * np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 5)


class Mix:
    def __init__(s, D): s.b = np.zeros((2, int(D * SR) + SR * 3))

    def add(s, x, t, pan=0.0, g=1.0):
        i = int(t * SR)
        if i >= s.b.shape[1] or i < 0: return
        x = x[: s.b.shape[1] - i]
        s.b[0, i:i + len(x)] += x * g * np.sqrt((1 - pan) / 2)
        s.b[1, i:i + len(x)] += x * g * np.sqrt((1 + pan) / 2)


def chord(root, sc, deg, add7):
    def note(d): return root + sc[d % 7] + 12 * (d // 7)
    ns = [note(deg), note(deg + 2), note(deg + 4)] + ([note(deg + 6)] if add7 else [])
    return ns


def compose(mood, bpm, D, lift=None, seed=0):
    global rng
    rng = np.random.default_rng(seed)
    M = MOODS.get(mood, MOODS["warm_piano"])
    root = 57 + [0, 2, 3, 5, 7, -2][seed % 6]  # key varies per video
    beat = 60 / bpm; bar = 4 * beat
    mx = Mix(D)
    lift = lift if lift is not None else min(D * 0.35, 8 * bar)
    nb = int(np.ceil(D / bar)) + 1
    for b in range(nb):
        t0 = b * bar
        deg, a7 = M["prog"][b % len(M["prog"])]
        ch = chord(root, M["sc"], deg, a7)
        full = t0 >= lift - 1e-3
        lvl = 0.75 if not full else 1.0
        for ins in M["inst"]:
            if ins == "piano_arp":
                pat = [0, 1, 2, 1, 3 if len(ch) > 3 else 2, 1, 2, 1]
                for i, p in enumerate(pat):
                    mx.add(piano(hz(ch[p % len(ch)] + 12 * (i == 4)), 1.6, .32 * lvl), t0 + i * beat / 2, rng.uniform(-.3, .3))
                mx.add(piano(hz(ch[0] - 12), bar, .35), t0, -.1)
            elif ins == "piano_sparse":
                if b % 2 == 0 or full:
                    for i in range(2):
                        mx.add(piano(hz(rng.choice(ch) + 12), 2.4, .22), t0 + i * 2 * beat + rng.uniform(0, beat / 2), rng.uniform(-.5, .5))
            elif ins in ("pad", "pad_dark"):
                for n in ch[:3]:
                    mx.add(pad(hz(n), bar + .4, .09, 900 if ins == "pad_dark" else 1600), t0, rng.uniform(-.4, .4))
            elif ins == "drone":
                mx.add(pad(hz(root - 24), bar + .5, .22, 400, 1.0), t0, 0)
            elif ins == "strings":
                for n in ch[:3]:
                    mx.add(strings(hz(n), bar + .3, .1 * lvl), t0, rng.uniform(-.5, .5))
                mx.add(strings(hz(ch[0] - 12), bar + .3, .12), t0, 0)
            elif ins == "ostinato" and full:
                for i in range(8):
                    mx.add(pluck(hz(ch[0] - 12 + (7 if i % 4 == 2 else 0)), beat, .35, .3), t0 + i * beat / 2, -.2)
            elif ins == "arp16":
                for i in range(16):
                    n = ch[[0, 1, 2, 1][i % 4]] + (12 if i % 8 >= 4 else 0)
                    mx.add(lp(sawtooth(2 * np.pi * hz(n) * tt(beat / 4)) * np.exp(-tt(beat / 4) * 14), 2600), t0 + i * beat / 4, .3 * (i % 2 * 2 - 1) * .5, .12 * lvl)
            elif ins == "epiano":
                for k, n in enumerate(ch):
                    mx.add(epiano(hz(n), bar * .95, .16), t0 + k * .015 + rng.uniform(0, .02), (k - 1.5) * .2)
            elif ins == "pluck_chords":
                for i in (0, 3, 6):
                    for k, n in enumerate(ch):
                        mx.add(pluck(hz(n + 12), beat * 1.2, .14, .6), t0 + i * beat / 2 + k * .008, (k - 1) * .3)
            elif ins == "marimba_arp":
                for i in range(8):
                    mx.add(marimba(hz(ch[[0, 2, 1, 2, 0, 1, 2, 1][i] % len(ch)] + 12), .9, .28 * lvl), t0 + i * beat / 2, rng.uniform(-.4, .4))
            elif ins == "strum":
                for i, sb in enumerate([0, 1.5, 2, 3]):
                    for k, n in enumerate(ch + [ch[0] + 12]):
                        mx.add(pluck(hz(n), 1.8, .16 * (1 if i % 2 == 0 else .7), .55), t0 + sb * beat + k * .012, (k - 2) * .15)
            elif ins == "stabs" and full:
                for sb in (0, 1.5, 3):
                    for n in ch:
                        mx.add(lp(sawtooth(2 * np.pi * hz(n) * tt(.18)), 2400) * np.exp(-tt(.18) * 9), t0 + sb * beat, 0, .1)
            elif ins == "clav":
                for sb in (0.5, 1.75, 2.5, 3.5):
                    for n in ch[1:]:
                        mx.add(hp(pluck(hz(n + 12), .25, .2, .9), 300), t0 + sb * beat, .2)
            elif ins == "bass_root":
                mx.add(bass(hz(ch[0] - 24), bar * .9, .38), t0)
            elif ins == "bass8" and full:
                for i in range(8):
                    mx.add(bass(hz(ch[0] - 24 + (12 if i % 4 == 3 else 0)), beat / 2 * .9, .32), t0 + i * beat / 2)
            elif ins == "funk_bass":
                for sb, o in ((0, 0), (.75, 12), (1.5, 0), (2.25, 10), (2.5, 12), (3.5, 7)):
                    mx.add(lp(pluck(hz(ch[0] - 24 + o), .3, .55, .7), 900), t0 + sb * beat)
        dr = M["drums"]
        if dr and (full or dr in ("shaker", "pulse")):
            for i in range(16):
                ts = t0 + i * beat / 4
                if dr == "shaker" and i % 2 == 0: mx.add(shaker(.18 if i % 4 else .1), ts, .3)
                if dr == "pulse" and i % 4 == 0: mx.add(lp(kick(.35), 200), ts)
                if dr == "four":
                    if i % 4 == 0: mx.add(kick(.6), ts)
                    if i % 8 == 4: mx.add(clap(.35), ts)
                    if i % 4 == 2: mx.add(hat(.18), ts, .25)
                if dr == "rock":
                    if i in (0, 6, 8, 10): mx.add(kick(.7), ts)
                    if i in (4, 12): mx.add(snare(.5), ts)
                    if i % 2 == 0: mx.add(hat(.15), ts, .25)
                if dr == "boombap":
                    sw = (beat / 4 * .25) if i % 2 else 0
                    if i in (0, 7, 10): mx.add(lp(kick(.55), 2500), ts)
                    if i in (4, 12): mx.add(lp(snare(.35), 5000), ts)
                    if i % 2 == 0: mx.add(lp(hat(.1), 9000), ts + sw, .3)
                if dr == "toms" and i in (0, 3, 6, 8, 11, 14): mx.add(tom(.4), ts, rng.uniform(-.3, .3))
                if dr == "funk":
                    if i in (0, 3, 10): mx.add(kick(.6), ts)
                    if i in (4, 12): mx.add(snare(.45), ts)
                    if i in (7, 15): mx.add(snare(.08), ts)
                    mx.add(hat(.12 if i % 2 == 0 else .06), ts, .25)
    x = mx.b[:, : int(D * SR)]
    if M.get("crackle"):
        c = (rng.random(x.shape[1]) > .9995) * rng.uniform(-1, 1, x.shape[1])
        x += lp(c, 4000) * .3 + lp(noise(x.shape[1] / SR), 6000) * .004
    ir_t = tt(2.2); ir = rng.standard_normal((2, len(ir_t))) * np.exp(-ir_t / .55)
    ir = np.array([lp(i, 6000) for i in ir]); ir /= np.abs(ir).sum(1, keepdims=True).max() / 6
    wet = np.array([fftconvolve(x[c], ir[c])[: x.shape[1]] for c in range(2)])
    y = hp(x + M["rev"] * wet, 35)
    fade = np.ones(y.shape[1]); n = int(min(2.5, D * .1) * SR); fade[-n:] = np.linspace(1, 0, n) ** 2
    fi = int(.3 * SR); fade[:fi] = np.linspace(0, 1, fi)
    y = np.tanh(1.2 * y / (np.abs(y).max() + 1e-9)) * fade
    y *= 10 ** (-16 / 20) / (np.sqrt((y ** 2).mean()) + 1e-9)
    return np.clip(y, -.98, .98)


def main():
    mood, bpm, D, out = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
    lift = float(sys.argv[5]) if len(sys.argv) > 5 and sys.argv[5] != "-" else None
    seed = int(sys.argv[6]) if len(sys.argv) > 6 else int(hashlib.md5(out.encode()).hexdigest(), 16) % 997
    y = compose(mood, bpm, D, lift, seed)
    import wave
    with wave.open(out, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((y.T * 32767).astype(np.int16).tobytes())
    print(f"music {mood} {bpm:.0f}bpm {D:.1f}s -> {out}")


if __name__ == "__main__":
    main()
