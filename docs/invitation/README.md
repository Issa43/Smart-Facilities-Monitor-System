# Graduation defense invitation — SFLMS

Modern invitations for the project defense, built as editable HTML and
rendered to PNG. All four keep the original content (title, team,
supervisor, date, time, venue, motto, closing lines). They use a modern,
dark AI and developer style (Alexandria, IBM Plex Sans Arabic, JetBrains
Mono), and every visual comes from the project itself.

| File | Concept | Size |
|------|---------|------|
| `01-ai-vision.html` | AI camera feed: isometric smart buildings with YOLO detections (`fire`, `smoke`, `person`), a HUD showing the defense date and time, lifecycle stages as `plan()` → `maintain()`, and the real tech stack | 3:4, 2400×3200 |
| `02-code-editor.html` | IDE layout: `defense.py` with the project's detector and handover logic, the invitation as a live Markdown preview, and a terminal and status bar | 3:4, 2400×3200 |
| `03-ai-core.html` | Keynote-style minimal design: an AI core with the five lifecycle stages orbiting it | 3:4, 2400×3200 |
| `04-story-ai-core.html` | 9:16 version of 03 for WhatsApp status and Instagram stories | 9:16, 2160×3840 |

The rendered images are in `png/`.

## Review of the original design

**Text fixes (used in all versions)**
- `أكثر ذكاء` → `أكثر ذكاءً` (the tamyīz needs tanwīn al-fatḥ).
- The closing line used `حضوركم` twice (`بحضوركم يكتمل نجاحنا.. وننتظر حضوركم`).
  It now reads `ونتطلّع إلى أن نشارككم ثمرة جهدنا في هذا اليوم المميّز`.
- `..` → `…` (the double dot is not a standard punctuation mark).
- The date now includes the weekday (13/10/2026 is a **Tuesday**, الثلاثاء), and the
  time appears in Arabic with the numeric time underneath (`الواحدة ظهراً` / `1:00 PM`).

**Design issues**
- Too much is happening at once: laptop, books, graduation cap, flowers, CCTV camera,
  and three floating panels all compete with the text.
- Some content appears twice. *Management / AI / Analytics / Security / Facilities*
  shows up both on the left sidebar and on the book spines.
- The AI-generated screens show a product that doesn't exist. The actual SFLMS
  dashboard (`screenshots/`) is more convincing and represents your real work.
- The best idea in the image is the lifecycle panel (*Plan → Design → Build →
  Operate → Maintain*), but it's small and off to the side. The redesigns make it
  the main visual theme because it *is* the project.
- The date, time, and venue row and the closing lines sit on top of busy imagery
  and very close to the bottom edge, which risks being trimmed when printed.
- The fonts are mixed without a clear system. The new versions use one Arabic
  display font, one Arabic text font, and one Latin font per design.

**Worth adding if available** (not added because it isn't in the original): the
university and faculty logos, and a clearer name for the venue for off-campus guests.
For example, write out which faculty the "سيمنار الأسنان" hall belongs to.

## Editing and re-rendering

Change the text directly in the HTML. Every poster is a single file, and fonts load
from Google Fonts. To regenerate the PNGs (uses the Playwright/Chromium install):

```bash
cd docs/invitation
NODE_PATH=$(npm root -g) node render.cjs                    # all posters
NODE_PATH=$(npm root -g) node render.cjs 03-ivory-emerald.html
```
