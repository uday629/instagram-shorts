# instagram-shorts — `/instagram-reels` Claude skill

Raw talking-head clip → finished 9:16 Instagram Reel / Short.
Claude studies the video and voice, finds the niche + emotion, matches the **genre editing matrix** (24 niches × B-roll, motion style, 4-color palette, font pair, music, SFX, delivery, hook, rhythm, notes), then edits:

- **Clean cut** – silences + retakes removed only when needed (already-edited sources keep their pacing)
- **Color correction** – measured white balance, levels, contrast, saturation (skin protected), only when the clip needs it
- **Captions** – golden-ratio lockups, composed layouts, 7 animation styles, any script (Bangla/Hindi via HarfBuzz)
- **Motion graphics** – hook card, vs/payoff graphic, quote card, lower third, highlight, underline, counters
- **Music** – original track synthesized per niche mood (no copyright)
- **SFX** – real CC0 recordings from the internet only (Freesound*, Kenney, USC SSE / Internet Archive, Wikimedia, this repo's mirror), with automatic fallbacks when a site is blocked
- **Mix + QA** – voice-first ducking, −14 LUFS, safe-zone + end-frame QA sheet

CPU only. Runs inside the claude.ai code-execution sandbox (free plan works) and in Claude Code.

## Install

**claude.ai (Free / Pro):**
1. Download `instagram-reels.zip` from this repo.
2. Settings → Capabilities → turn on **Code execution and file creation**. Under network access allow at least package managers; "All domains" gives the best SFX/font choice.
3. Settings → Capabilities → Skills → **Upload skill** → choose the zip.
4. New chat → attach your raw video → type `/instagram-reels`.

**Claude Code:**
```bash
git clone https://github.com/uday629/instagram-shorts && cp -r instagram-shorts/instagram-reels ~/.claude/skills/
```

## Layout
```
instagram-reels/            the skill (zip this folder)
  SKILL.md                  workflow (short on purpose = fewer tokens)
  references/plan.md        edit-plan schema
  references/rules.md       design + cut rules
  data/niches.json          the genre matrix (from talking_head_genre_editing_matrix_upgraded.xlsx)
  data/motion.json          motion-style guide
  scripts/                  setup, analyze, asr, style, fonts, music, sfx, render, qa
sfx-pack/                   CC0 SFX mirror (fallback when other sites are blocked) + CREDITS.txt
```
Releases → `models-v1` holds faster-whisper `tiny/base/small` (MIT) as a fallback when Hugging Face is blocked.

\* Freesound is used only if you set `FREESOUND_TOKEN` (free API key).

## Licenses
Code: MIT. SFX pack: CC0 (Kenney.nl; USC Sunset Editorial / SSE library via Internet Archive). Fonts are downloaded at run time from Google Fonts (OFL). Whisper models: MIT (OpenAI / Systran).
