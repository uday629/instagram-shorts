"""Word-level transcript with faster-whisper on CPU. Model source chain: HF -> HF mirror -> GitHub release.
usage: asr.py audio16k.wav [lang|auto] [tiny|base|small]   -> work/transcript.json"""
import os, sys, tarfile, urllib.request
from lib import wp, jsave

GH = "https://github.com/uday629/instagram-shorts/releases/download/models-v1/faster-whisper-{m}.tar"


def load(size):
    from faster_whisper import WhisperModel
    kw = dict(device="cpu", compute_type="int8", cpu_threads=os.cpu_count() or 2)
    errs = []
    for ep in (None, "https://hf-mirror.com"):
        try:
            if ep:
                os.environ["HF_ENDPOINT"] = ep
            return WhisperModel(size, **kw)
        except Exception as e:
            errs.append(str(e)[:80])
    d = wp(f"fw-{size}")
    try:
        if not os.path.exists(os.path.join(d, "model.bin")):
            t = wp("m.tar")
            urllib.request.urlretrieve(GH.format(m=size), t)
            with tarfile.open(t) as tf:
                tf.extractall(d)
            os.remove(t)
        sub = [r for r, _, f in os.walk(d) if "model.bin" in f][0]
        return WhisperModel(sub, **kw)
    except Exception as e:
        errs.append(str(e)[:80])
    print("ASR_UNAVAILABLE", " | ".join(errs))
    return None


def main():
    wav = sys.argv[1]
    lang = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] != "auto" else None
    size = sys.argv[3] if len(sys.argv) > 3 else os.environ.get("REEL_ASR", "base")
    m = load(size) or (load("base") if size != "base" else None)
    if not m:
        jsave(wp("transcript.json"), dict(ok=False))
        return
    segs, info = m.transcribe(wav, language=lang, word_timestamps=True, vad_filter=True, beam_size=1,
                              condition_on_previous_text=False)
    words, lines, lp = [], [], []
    for s in segs:
        lp.append(s.avg_logprob)
        lines.append([round(s.start, 2), round(s.end, 2), s.text.strip()])
        for w in s.words or []:
            words.append([w.word.strip(), round(w.start, 2), round(w.end, 2)])
    conf = round(sum(lp) / max(len(lp), 1), 2)  # > -0.6 good, < -0.9 unreliable text (timings still usable)
    jsave(wp("transcript.json"), dict(ok=True, lang=info.language, conf=conf, words=words, lines=lines))


if __name__ == "__main__":
    main()
