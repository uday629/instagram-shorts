# Hard rules (edit to the message, not to effects)

## Decide from the content
- Brief first (internal): topic → core message → emotion per line → audience. Every choice below must serve it.
- Row = default for B-roll idea, motion style, palette, fonts, music, SFX, delivery, hook, rhythm. The row's NOTES are constraints (e.g. label illustrative numbers, no guaranteed returns, no shaming, no diagnosis).
- Calm/reflective → blur/rise/word, warm or neutral tint, soft SFX, slow push. Urgent/motivational → slam/pop, contrast, impacts only on the main payoff. Comedy → pop + timing pauses. Serious/news/crime → type/rise, cool, no playful bounce.

## Captions (typography)
- Caption meaning, not every word. 1–3 word key; lead carries context; never a lone filler lead (is, a, I, the, so).
- Golden ratio: lead = key ÷ 1.618 (never < key ÷ 2.6). Lead sits tight above the key. Lead never wider than the key.
- Two clearly different faces (bold sans key + light/italic lead). The script handles sizes/fonts; you choose words.
- Rhythm: vary layout L → R → C → I and use 2–3 animations deliberately. Never all left, never one style.
- Accent color on ≤ 25 % of captions (numbers, the turning word). Highlight (`hl`) / underline (`ul`) ≤ 3 per video.
- Caption spans must cover the full spoken phrase; a caption is never cut off (script enforces ≥ read time; QA checks end frames).
- Safe zone: x 6–85 %, y 12–80 % (IG UI). Keep captions off the face (default y 0.655).

## Motion graphics
- MG must translate the meaning: hook title card in the first 2 s (`card`), payoff/contrast line as a designed graphic (`vs` or `quote`), names/sources as `lower`. Max ~1 MG per 8–10 s. No clip-art, no literal stick figures.
- MG owns the screen: captions under vs/quote are hidden automatically.

## Cuts & movement
- Raw single take: remove silences (auto), retakes and stumbles (`remove`). Keep natural breaths; no flash frames (< 4 frames are dropped).
- Already-edited source (`edited` true): `cut:none`, keep its pacing, no extra zoom steps.
- Wide shot → punch-in alternation on jump cuts (auto); tight shot → minimal zoom. Use `punch` only on 2–4 key moments.

## Sound
- Voice is king: music ducks under speech (auto), master −14 LUFS.
- Music mood from the row; `lift` at the payoff so energy rises with the message. Mood `none` for serious/grief topics if music would feel disrespectful.
- SFX sparingly: auto spacing ≥ 1.3 s; add `sfx_add` only for real accents. Never synthesize SFX.

## QA (before delivering)
- `qa.py` ISSUES must be `none`. In `qa.jpg` check: every caption's end frame fully readable, no half-shown words, no caption over the face/mouth, cuts clean (cut−1 / cut+1 frames), MG finished before scene changes.
