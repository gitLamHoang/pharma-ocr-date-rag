# Design direction

The working rules for every screen. Tokens live in `src/styles/tokens.css`; shared primitives
(shell, buttons, fields, segmented control, pills) in `src/styles/app.css`. Components use
semantic tokens only, never raw hex or the scales.

## The product and its one question

A reviewer on a pharmaceutical quality team uploads a document and confirms every date in it.
Each screen answers one question first:

- **Documents:** "Which documents still have dates waiting for me?" The needs-review count is the
  loudest figure on the screen and the only one in sunflower.
- **Review:** "Is this date what the page says, and is it the right kind of date?" The page image
  with its highlight boxes is the largest block; the selected date is the only sunflower mark on it.

Use is long sessions at a desk (1280 px and up), sometimes a tablet (834 px) in a QA office.
Dense, calm, every figure traceable to the page.

## Style: framed sheet

Dealt from the taste-skill app library (`framed-sheet`, seed 1329022108), brand palette and type kept.

- **The frame** is one tinted ground (`--bg`: powder in light, deepest navy in dark) holding the
  48 px top bar. No rule between the bar and the frame.
- **The sheet** (`.sheet`) holds the work: `--surface`, inset 8 px from the window's left, right
  and bottom edges, 16 px radius, 1 px `--border`, no shadow, 24 px padding. Nothing nests deeper
  than frame → sheet → panel.
- **No sidebar.** The product has two destinations (Documents, and Review of one document), so the
  top bar carries the mark and name, the nav (underline tab), the AI/offline status and the theme
  switch. Review breadcrumbs back to Documents from its title row.
- **Below 640 px** the frame disappears: the sheet becomes the screen under the bar.

## Palette (60 / 30 / 10)

| Role | Light | Dark |
|---|---|---|
| Frame `--bg` | powder-100 | navy-950 |
| Sheet `--surface` | white | navy-900 (Midnight Navy) |
| Panel, page-viewer backdrop `--surface-2` | powder-50 | navy-800 |
| Ink `--text` | navy-900 | near-white |
| Secondary `--muted` | navy grey, 5.0:1 or more | powder grey, 6.0:1 or more |
| Accent `--accent` | sunflower | sunflower |

- **Sunflower is for four things only:** the primary action (one per screen), the selected date
  (row and its box on the page), the focus ring, and the needs-review count (`.pill--review`).
  Never body text, never a decorative fill, never a second button.
- Text on sunflower is always `--accent-ink` (navy).
- Status is ink on its own pale tint: `--danger`, `--warning`, `--info`, `--positive` with
  `--*-bg`. One status mark per row.
- **Dark theme is Midnight Navy by brief.** (The taste library prefers neutral darks; the spec's
  palette wins.)

### Date families

Seven hues, spaced around the wheel, none of them sunflower (reserved for selection) and none
violet or indigo (hue 244-295°, `tokens.test.ts` checks this):

| Family | On page images `--fam-*` | UI dots/labels `--fam-*-ui` (dark) |
|---|---|---|
| Product / batch | teal `#0F766E` | `#5CC8BA` |
| Document control | blue `#1F5FBF` | `#93B6F2` |
| Signature | rose `#B4235A` | `#F394B8` |
| Legal / regulatory | stamp magenta `#8F2B86` | `#E39BDF` |
| Audit / inspection | rust `#A34A07` | `#F2A868` |
| Logistics | olive `#4B6F12` | `#B0D16E` |
| Other | slate `#5B6478` | `#B5BCCD` |

- Page images are paper in both themes, so `--fam-*` never changes with the theme. Every one is
  4.5:1 or more on white and on off-white scan paper (`tokens.test.ts` checks this).
- **Highlight box:** 2 px stroke in the family colour, fill at 12 % of it (`color-mix`), 2 px
  radius, drawn just outside the word box so the date stays readable.
- **Selected box:** 3 px sunflower stroke, 30 % sunflower fill, a 1 px navy ring outside it so it
  holds on white paper. One date at a time, or every date of the flag the reviewer clicked.
- In lists, the family shows as an 8 px dot plus the family's label in `--fam-*-ui`; the row's text
  stays in ink. Never a coloured row background, never a coloured left border.

## Type

One family at two widths, plus a mono with one job. All OFL, self-hosted via @fontsource.

| Role | Face | Size / weight |
|---|---|---|
| Page title `h1` | Archivo, condensed (`font-stretch: 68%`) | 28 / 700 |
| Section, panel group `h2` | Archivo condensed | 20 / 700 |
| Card or panel title `h3` | Archivo, normal width | 16 / 600 |
| Body, cells, controls | Archivo | 14 / 400–500 |
| Secondary cells, sublines | Archivo | 13 / 400 |
| Table headers, meta, pills | Archivo | 12 / 500 |
| Dates, ISO values, raw text, IDs, model name | Fragment Mono (`.mono`) | inherit |

- Five sizes do the work: 12, 13, 14, 20, 28 (16 for card titles). Fixed rem, never fluid.
- Sentence case everywhere. No uppercase tracked labels.
- Tabular figures on the body (`font-variant-numeric: tabular-nums`); numbers right-aligned in columns.
- Condensed width is for headings and the wordmark only, never for labels, buttons or data.

## Density and grid

- 4 px base. One gutter, `--gap` 16 px, used horizontally and vertically.
- Controls 32 px tall (`--control-height`), 6 px radius. Table rows 44 px (`--row-height`) for one
  line; 56–64 px when a row carries a subline.
- Radii: sheet 16, card/panel 8, control 6, chip 4. Nothing else.
- Table headers: 12 px muted, sentence case, no fill band, no rule under them. Row rules 1 px
  `--rule`. No zebra.
- **Documents** (sheet content 1214 px at 1280: 1280 − 2×8 inset − 2×1 edge − 2×24 padding): title row (h1, then `.title-row__actions` with upload as the one primary
  button on the right), drop zone as a 1 px dashed `--control` band 96 px tall across the full
  width, then the table. Columns: name (widest, truncates with ellipsis), pages, status, dates,
  flags, needs review, uploaded at; counts right-aligned; needs review as `.pill--review` when
  above zero and a plain `0` otherwise; status as a pill (queued/reading/classifying/validating in
  `--info`, done plain, failed `--danger`); a failed row carries the server's message as its
  subline under the name, in `--danger`. Counts print as an em dash until the run is done. The
  list refreshes every 2 s while any run is still moving. When AI is off, a `.notice` line under
  the title row reads "AI classification off — rules only".
- **Review** (sheet): title row (breadcrumb "Documents /" then the filename as h1; export and
  reprocess on the right). Below it a two-column split: page viewer `minmax(0, 1fr)` and date
  panel `400px`, 16 px apart (1214 = 798 + 16 + 400 at 1280). The viewer sits on `--surface-2` with an
  80 px thumbnail rail on its left and zoom controls in its header (50–300 %, 100 % fits the page
  to the width); the date panel is the sheet itself, flags first (errors first, five shown, then
  "Show all N flags"), then dates grouped by family (`h2` per family with its count). From 961 px
  the sheet fills the window under the top bar: the viewer takes the full height and the date panel
  scrolls on its own. The title row's right side carries the needs-review count (`.pill--review`)
  and the date count.
- **Date row:** value first (mono, 600; a month-only date as `2027-03` plus `Mar 2027` in muted; an
  ambiguous one as both readings joined by "or", never one value), its status pill on the right;
  the type label; then the raw text in mono, page, source and confidence in 13 px muted; then the
  page's words around the date, the date itself in ink. The selected row takes `--selected-bg` and
  the active one a 1 px sunflower ring; only the active row shows its actions (Accept `A`,
  Edit `E`, Reject, History). ↑/↓ move, A accepts, E edits; shortcuts are off while typing, and ↑/↓ are left to the
  page canvas (focusable, to scroll a zoomed page) and the thumbnail rail when they have focus.
- **Read-only runs:** an older run (`?run=N`) or a run a review found replaced (HTTP 409) shows a
  `.notice` with the way back ("Open the latest run", or "This run was replaced — reload" with a
  Reload button in `--danger` tint) and no decision controls; the title's needs-review count drops
  its sunflower and reads "need review in this run". A `?run=` that is not an older run of this
  document is ignored when newer than the latest, and refused ("Run N is not a run of this
  document.") when the server does not know it or its dates name another document.
- **Export and reprocess** sit after the count in the title row, both secondary buttons (Review
  has no sunflower button: its sunflower is the selected date). **Export** opens a menu of two
  download links, "Export CSV" and "Export JSON", each with a one-line hint; it exports the run on
  screen (a frozen run exports its own dates) and shows only once that run's dates are loaded.
  Escape or a click elsewhere closes it. **Reprocess** asks first in a dialog ("Reprocess this
  document?": what the new run reads, the exact-match carry-over rule, that the old run stays as a
  read-only record), then switches the screen to the new run, follows it while it moves, and once
  it is done says "Run N replaced run M. K decisions carried over." in a `.notice`. It is disabled
  (with the reason for screen readers) while a run is moving, and offered on a failed run as the
  way to retry.
- **History** (under the active row, History button): decisions newest first, each "Accepted by
  name · time" (`<time>`, local `YYYY-MM-DD HH:MM`), what changed, the reason, and "Carried over
  from run N" once for a carried decision.
- **Discarded AI suggestions:** a collapsed `<details>` at the foot of the date panel, after a
  1 px `--rule`, titled with its count; absent when the run discarded nothing. Each item shows the
  AI's own words (verbatim text in mono, evidence in quotes), the page, what kind of suggestion it
  was and the reason it was discarded. Never a date: no ISO value, no box on the page, no actions,
  not exported.
- **Tablet (834 px):** Documents keeps the table and moves uploaded-at under the name as a subline
  (from 960 px down). Below 640 px it keeps name, status and needs review as columns and moves
  pages, dates and flags to a subline ("3 pages · 12 dates · 2 flags").
  Review stacks the viewer (50 vh, sticky at the top of the window) above the date panel, which
  scrolls under it; the thumbnail rail becomes a horizontal strip. Below 640 px the Review title
  row puts the count on its own line with export and reprocess together under it.

## Components

- **Buttons** (`.button`): secondary is surface with a 1 px `--control` edge; `--primary` is
  sunflower with navy ink, one per screen; `--quiet` has no edge; `--danger` is red ink on the
  secondary shape. Disabled stays readable (muted ink on `--surface-2`) and says why nearby.
- **Fields** (`.field`, `.input`): label above, 8 px gap, hint below tied with `aria-describedby`;
  invalid state is a `--danger` edge plus the message in words.
- **Segmented** (`.segmented`): native radios, as wide as its options.
- **Pills** (`.pill--*`): 20 px, 12 px text, ink on its own tint, never squeezed (`flex: none`).
- **Source:** "Rules" or "Rules + AI" as plain text; an AI-only date is `.pill--info` with the
  words "AI-only · verify". Confidence is a labelled number ("Confidence 0.92"), never a bar.
- **Dialogs** (review: accept/correct/reject; reprocess) and the export menu are the only things
  that float, so the only places a shadow appears (`--shadow-float`; dialogs over `--scrim`); use
  `<dialog>` for focus trapping. Reviewer (remembered in
  this browser) and reason are required; a correction offers the type picker grouped by family,
  and for a date with two readings only those readings as radios, never a free value. A
  month-only date takes only `YYYY-MM`: the dialog (and the server) refuse a day.
- **Focus:** a 2 px `--focus-edge` outline plus a sunflower halo, on every interactive element.
  On the page canvas the ring is an inset layer over the canvas, since the scrolled page would
  cover an outline.

## States

- **Loading:** the final layout with flat bars at each value's real size (`--active` on the
  sheet, where `--surface-2` would not show); no
  shimmer, no spinner in content, no layout shift when data lands.
- **Empty:** the block keeps its frame and header plus one sentence that names the next step
  ("No documents yet. Drop a PDF or scan here, or choose a file.").
- **Error:** inside the block that failed, one sentence with what failed and a Retry text button;
  the server's `detail` message shown as written.
- **Zero** prints as `0`; missing values are an em dash in `--muted`.
- **Offline mode** (AI off) is a mode, not an error: a grey dot and "Rules only" in the top bar.
- **Static build** (GitHub Pages, `VITE_MODE=static`): one line in the frame under the top bar on
  every screen, aligned with the brand, 13 px: "Runs in your browser" in ink 500, then "rules only
  (no AI) · documents are not uploaded anywhere · every date needs review" in muted, wrapping only
  after a dot. No tint, no box, no sunflower. It replaces the Documents "AI classification off"
  notice, which would repeat it.

## Motion

State changes only: 120–180 ms, `--ease-out`, transform and opacity (plus colour on hover).
A selected box may scroll into view smoothly; upload progress may animate its bar. No entrances,
no page-load choreography. `prefers-reduced-motion` drops durations to zero.

## Do / don't

Do:
- Show the page's own words next to every date (raw text in mono, context snippet in muted).
- Keep every figure on one right edge per column and every date in ISO (`2026-03-14`, month
  precision as `2027-03`).
- Name the action on every control ("Accept date", "Export CSV"), and say what went wrong and how
  to recover in every error.

Don't:
- Gradients, glass, glows, decorative shadows, emoji, icons in tinted squares, sparklines.
- Violet/indigo accents, sunflower anywhere outside its four jobs, body text in sunflower.
- Eyebrow labels above headings, uppercase tracked headers, section numbers.
- A hero header, a greeting, or filler copy. Titles are nouns: "Documents", the filename.
- Product branding of any company; the product is "Pharma dates".
- Fetching from components: all data goes through `api` (`src/api/index.ts`, the `DataSource`
  interface).
