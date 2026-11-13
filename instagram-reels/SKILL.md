---
name: instagram-reels
description: Edit a raw talking-head clip into a finished Instagram Reel / Short (9:16). Studies the video and voice, detects niche + emotion, matches the genre editing matrix (fonts, 4-color palette, motion style, music, SFX), cleans bad takes and silences, color-corrects, adds captions, motion graphics, original music and CC0 SFX, then renders and QA-checks. Use when the user uploads a video and types /instagram-reels or asks to edit a reel/short/talking-head video. CPU-only; works in claude.ai code execution (free plan) and Claude Code.
---

# /instagram-reels

Goal: best possible edit with the fewest tokens. **Work silently.** No progress narration, no explaining steps, no echoing script output. Speak to the user only to (a) ask the one blocking question below, or (b) deliver.

`$S` = the folder containing this SKILL.md (claude.ai: usually `/mnt/skills/user/instagram-reels`). Work dir = `work/` in cwd (scripts create it). Input on claude.ai: `/mnt/user-data/uploads/<file>`; output goes to `/mnt/user-data/outputs/reel.mp4` automatically (else `./reel.mp4`).

## Pipeline
1. `bash $S/scripts/setup.sh` (quiet, idempotent).
2. `python3 $S/scripts/analyze.py RAW [lang]` → read its short summary, then view `work/sheet.jpg` once (6 frames, caption-zone guides). Pass `lang` (`en`, `bn`, `hi`…) if obvious; otherwise `auto`.
3. Decide (in your head, not in chat): topic, core message, audience, emotion arc (hook → build → payoff → CTA), niche row(s).
   `python3 $S/scripts/style.py` lists the 24 niches; `python3 $S/scripts/style.py ID [ID2]` prints the chosen row(s). Use 2 IDs when the video spans niches (e.g. money mindset = 4 + 1); the first ID leads the look.
4. **Blocking question (only if needed):** if the transcript is `NONE` or `LOW` and the speech is not clearly understandable, ask once: "Paste the script (or the key lines) of this video." Timings still come from ASR/VAD, so only text is needed. Never ask anything else; choose sensible defaults.
5. Write `work/plan.json` per `references/plan.md` (read it the first time). Rules in `references/rules.md` are hard constraints.
   Write the captions yourself (one per meaningful phrase, ~1 per 1.5–3 s, key = the word that carries the meaning, in the speaker's language/script) using transcript timings — far better than `"captions":"auto"`, which is only a fallback. Add a hook `card` (0–2.5 s), one payoff graphic (`vs`/`quote`), `music.lift` at the payoff, 2–4 `punch` moments.
6. `python3 $S/scripts/render.py work/plan.json` (resumable). If a call may exceed the tool time limit (> ~60 s of video or slow box), run `--part 1/3`, `--part 2/3`, `--part 3/3` as separate calls; the last one muxes.
7. `python3 $S/scripts/qa.py OUT` → view `work/qa.jpg` once. Fix every `ISSUES` item and anything visibly wrong (cut-off/half words, unreadable line, caption on the face, flash frame, wrong emotion) by editing the plan, delete `work/part*`, re-render. Max 2 fix rounds.
8. Deliver: the file + max 4 short lines: niche/look, what was cleaned (cuts, grade), music mood, SFX credits line (from `work/sfx/credits.txt`, all CC0). Nothing else.

## Decisions the scripts already make (don't redo them)
- **Cut:** `needs_cut` false (already clean or already edited with its own shots) → plan `"cut":"none"`. Otherwise silence removal is automatic; add retakes to `remove` (source seconds). `"remove":"auto"` uses detected retakes (only when transcript confidence is good) — verify them against the transcript first.
- **Color:** grade is measured (white balance, levels, contrast, saturation, skin protected) and only applied when needed; niche tint is always subtle. Override with `"grade":"none"|"force"`.
- **Palette:** text/accent colors are auto-adjusted for WCAG contrast on the real footage; log appears in `work/layout.json`.
- **Fonts:** downloaded per row (Google Fonts, OFL). Bengali/Devanagari/Arabic captions switch to matching script fonts automatically.
- **Music:** original track synthesized for the row's mood/BPM (no copyright). Set `music.lift` to the payoff moment (source s) so the full arrangement enters there. User-supplied track: `"music_file"`.
- **SFX:** real recordings only, never generated: Freesound (if `FREESOUND_TOKEN`), Kenney CC0 mirrors on GitHub, USC SSE library (archive.org, CC0), the skill's own CC0 pack, Wikimedia Commons. Blocked site → next source automatically. Placement is automatic from caption/MG events and row roles; add hand-placed hits with `sfx_add`.

## Free-plan / sandbox notes
- CPU only; everything is pip wheels + a static ffmpeg (imageio-ffmpeg, has HarfBuzz text shaping). No apt.
- ASR = faster-whisper `base` int8 (HF → hf-mirror → GitHub release). If all are blocked, transcript is NONE → step 4.
- Upload limit is small on claude.ai; if the raw is too big, ask the user to trim/compress (720p is fine; output is 1080×1920).
- Network fully blocked → fonts fall back, SFX may be missing (`SFX_MISSING` lines): deliver without SFX and say so in one line.
