"""QA: one contact sheet (end frame of every caption/MG beat + frames around cuts, safe zones drawn) + automatic checks.
usage: qa.py reel.mp4  -> work/qa.jpg ; prints issues (empty = pass)"""
import sys, re, subprocess
import numpy as np
from PIL import Image, ImageDraw
from lib import W, H, wp, jload, ffmpeg, probe


def grab(path, t):
    r = subprocess.run([ffmpeg(), "-v", "error", "-ss", f"{max(0, t):.3f}", "-i", path, "-frames:v", "1", "-vf", "scale=270:480",
                        "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True)
    return Image.frombuffer("RGB", (270, 480), r.stdout, "raw", "RGB", 0, 1) if len(r.stdout) == 270 * 480 * 3 else None


def main():
    out = sys.argv[1]
    L = jload(wp("layout.json"))
    issues = []
    P = probe(out)
    if P["w"] != W or P["h"] != H: issues.append(f"size {P['w']}x{P['h']}")
    shots = []
    for c in L["caps"]:
        shots.append((c["t"][1] - .07, f"end:{c['key'][:10]}"))
        x0, y0, x1, y1 = c["box"]
        if x0 < W * .05 or x1 > W * .86 or y0 < H * .1 or y1 > H * .8:
            issues.append(f"caption '{c['key']}' outside safe zone {c['box']}")
        if c["t"][1] - c["t"][0] < .7: issues.append(f"caption '{c['key']}' on screen only {c['t'][1] - c['t'][0]:.2f}s")
    for g in L["mg"]:
        shots.append(((g["t"][0] + g["t"][1]) / 2, g["type"])); shots.append((g["t"][1] - .07, g["type"] + ":end"))
    for c in L["cuts"][:8]:
        shots.append((c - 1 / 30, "cut-1")); shots.append((c + 1 / 30, "cut+1"))
    for a, b in zip(L["cuts"], L["cuts"][1:]):
        if b - a < .15: issues.append(f"flash shot {a:.2f}-{b:.2f}")
    shots = sorted(shots)[:24]
    cols = 6; rows = (len(shots) + cols - 1) // cols
    S = Image.new("RGB", (270 * cols, 500 * max(rows, 1)), "black")
    d = ImageDraw.Draw(S)
    for i, (t, lab) in enumerate(shots):
        im = grab(out, t)
        if im is None: continue
        x, y = (i % cols) * 270, (i // cols) * 500
        S.paste(im, (x, y))
        dd = ImageDraw.Draw(S)
        dd.rectangle([x + int(270 * .05), y + int(480 * .1), x + int(270 * .86), y + int(480 * .8)], outline=(0, 255, 0))
        d.text((x + 4, y + 482), f"{t:.2f} {lab}", fill="yellow")
    S.save(wp("qa.jpg"), quality=82)
    r = subprocess.run([ffmpeg(), "-hide_banner", "-i", out, "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True).stderr
    I = re.findall(r"I:\s+(-?[\d.]+) LUFS", r); pk = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", r)
    if I and abs(float(I[-1]) + 14) > 1.5: issues.append(f"loudness {I[-1]} LUFS (target -14)")
    if pk and float(pk[-1]) > -1.0: issues.append(f"true peak {pk[-1]} dBFS")
    print(f"qa sheet {wp('qa.jpg')} | {P['dur']:.1f}s | LUFS {I[-1] if I else '?'} peak {pk[-1] if pk else '?'}")
    print("ISSUES: " + ("; ".join(issues) if issues else "none"))


if __name__ == "__main__":
    main()
