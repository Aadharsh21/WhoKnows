# Site design notes

Subject: ten teammates and their agents, the night before a 9 AM capstone demo.
Audience: hackathon judges first, students second. Job: get the idea in one look, then play it.

## Plan

Color (night over a dorm, two lights that mean something)
- night   #0E1330  page, deep indigo rather than black
- panel   #161C44  phones and panels
- brick   #222A5C  the building
- ink     #EEF0FF  text; ink-dim #A8B0DB
- lamp    #FFC46B  a person's light: awake windows, things people type
- agent   #8FB3FF  agent traffic: pulses between windows
- stop    #FF8C7A  anything a gate blocked

Type: Recursive only, using its axes to say who is talking.
- Casual axis on: what people type (and the human half of the headline)
- Linear: what agents say, and the interface
- Mono axis on: file paths, diffs, the clock

Layout
- Left-aligned text column for the hook, then the player at full width:
  [Nina's phone] [building stage, caption, controls, timeline] [the other phone]
- The building has ten windows, one per teammate. Lit means awake. Every window has a small
  agent light that never goes out, which is the headline made visible.
- Messages fly between agent lights. Blocked ones stop halfway in red.
- The sky is the one big motion: it turns from night to dawn as the story reaches 7 AM.
- Mobile: stage, caption, controls, then the two phones as tabs.

## Review against the usual defaults
- Not cream and serif, not black with a neon accent: indigo night with warm lamps and cool agent light.
- No all-caps eyebrows, no numbered markers except the timeline (which is a real sequence).
- No card grid: the explainer is a plain two-column list with real examples from the run.
- Motion is tied to the story (pulses, lights, sky), not decoration on scroll.
