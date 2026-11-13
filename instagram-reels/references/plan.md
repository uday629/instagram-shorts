# work/plan.json — schema (all times = SOURCE seconds, as printed by analyze.py)

```json
{
  "niche": [4, 1],                 // row ids, first leads the look
  "cut": "auto",                   // auto | none
  "remove": [[12.4, 15.1]],        // retakes / mistakes to drop, or "auto"
  "trim": [0.3, 58.0],             // optional hard in/out
  "grade": "auto",                 // auto | none | force
  "tint": "warm",                  // optional override: neutral warm cool sepia contrast
  "palette": {"accent": "#E58A3A"},// optional brand override (primary/secondary/neutral/accent)
  "anims": ["blur", "rise", "word"],// optional, else row preset. pop rise blur word slam type count
  "captions": [                    // or "auto" (from transcript; only when transcript text is reliable)
    {"t": [3.2, 5.0], "kt": 4.1, "key": "habits", "lead": "aware of my", "acc": "",
     "anim": "rise", "layout": "L", "accent": false, "hl": false, "ul": false, "punch": false, "y": 0.66}
  ],
  "emphasis": ["money", "never"], // auto-caption keywords to make the key
  "mg": [
    {"type": "card",  "t": [0.2, 2.6], "title": "3 money rules", "sub": "nobody told you"},
    {"type": "vs",    "t": [40.1, 43.0], "a": "Knowing", "b": "Hoping", "mid": "vs"},
    {"type": "quote", "t": [20.0, 24.0], "text": "Discipline is\nremembering what\nyou want"},
    {"type": "lower", "t": [1.0, 4.0], "title": "Dr. Name", "sub": "Nutritionist"}
  ],
  "broll": [{"file": "/mnt/user-data/uploads/broll1.mp4", "t": [10.0, 12.5]}],
  "punch": [[30.2, 31.5]],         // extra eye-anchored punch-ins
  "zoom": "auto",                  // auto | none
  "music": {"mood": "warm_piano", "bpm": 78, "gain": -24, "lift": 30.2},  // mood "none" = no music
  "music_file": null,
  "sfx": "auto",                   // auto | none
  "sfx_add": [[30.1, "impact"]],
  "look": null,                    // "grain" adds film grain
  "vignette": false,
  "out": null                      // default /mnt/user-data/outputs/reel.mp4 or ./reel.mp4
}
```

Caption fields: `t` phrase span; `kt` when the key word is spoken (key animates in then; default = `t[0]`);
`key` 1–3 meaningful words (big, headline font); `lead` small line above (key ÷ 1.618, italic/light face) — drop fillers;
`acc` optional small line under the key in the secondary color; `layout` L | R | C | I (inline);
`accent` key in accent color (numbers, the one word that matters); `hl` marker sweep behind key; `ul` hand-drawn underline;
`punch` eye-anchored push-in while the caption is up; `y` vertical center (0.58–0.74; default 0.655, tight face 0.70);
`caps` uppercase key.

Moods: warm_piano ambient drone cinematic pulse lofi groove marimba acoustic driving orchestral funk.
SFX roles: whoosh whoosh_soft click tick tap pop impact impact_soft riser paper pencil keyboard typewriter camera heartbeat breath phone_buzz stamp glitch boing scratch door ding coins footstep.
