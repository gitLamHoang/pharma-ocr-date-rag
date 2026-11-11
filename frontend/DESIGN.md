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

Seven hues, spaced around the wheel, none of them sunflower (reserved for selection):

| Family | On page images `--fam-*` | UI dots/labels `--fam-*-ui` (dark) |
|---|---|---|
| Product / batch | teal `#0F766E` | `#5CC8BA` |
| Document control | blue `#1F5FBF` | `#93B6F2` |
| Signature | rose `#B4235A` | `#F394B8` |
| Legal / regulatory | plum `#7E2E9A` | `#D6A2EA` |
| Audit / inspection | rust `#A34A07` | `#F2A868` |
| Logistics | olive `#4B6F12` | `#B0D16E` |
| Other | slate `#5B6478` | `#B5BCCD` |

- Page images are paper in both themes, so `--fam-*` never changes with the theme. Every one is
  4.5:1 or more on white and on off-white scan paper (`tokens.test.ts` checks this).
- **Highlight box:** 2 px stroke in the family colour, fill at 12 % of it (`color-mix`), 2 px
  radius, drawn just outside the word box so the date stays readable.
- **Selected box:** 3 px sunflower stroke, 30 % sunflower fill, a 1 px navy ring outside it so it
  holds on white paper. Only one at a time.
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
- **Documents** (sheet, 1232 px usable at 1280): title row (h1, then upload as the one primary
  button on the right), drop zone as a 1 px dashed `--control` band 96 px tall across the full
  width, then the table. Columns: name (widest, truncates with ellipsis), pages, status, dates,
  flags, needs review, uploaded at; counts right-aligned; needs review as `.pill--review` when
  above zero and a plain `0` otherwise; status as a pill (queued/reading/classifying/validating in
  `--info`, done plain, failed `--danger` with the error as its subline).
- **Review** (sheet): title row (breadcrumb "Documents /" then the filename as h1; export and
  reprocess on the right). Below it a two-column split: page viewer `minmax(0, 1fr)` and date
  panel `400px`, 16 px apart (1232 = 816 + 16 + 400). The viewer sits on `--surface-2` with an
  80 px thumbnail rail on its left and zoom controls in its header; the date panel is the sheet
  itself, flags first, then dates grouped by family (`h2` per family with its count).
- **Tablet (834 px):** Documents keeps the table and moves uploaded-at under the name as a subline.
  Review stacks the viewer (60 vh) above the date panel; the thumbnail rail becomes a horizontal
  strip.

## Components

- **Buttons** (`.button`): secondary is surface with a 1 px `--control` edge; `--primary` is
  sunflower with navy ink, one per screen; `--quiet` has no edge; `--danger` is red ink on the
  secondary shape. Disabled stays readable (muted ink on `--surface-2`) and says why nearby.
- **Fields** (`.field`, `.input`): label above, 8 px gap, hint below tied with `aria-describedby`;
  invalid state is a `--danger` edge plus the message in words.
- **Segmented** (`.segmented`): native radios, as wide as its options.
- **Pills** (`.pill--*`): 20 px, 12 px text, ink on its own tint, never squeezed (`flex: none`).
- **Source badge:** "Rules" is a plain pill; "AI-only" is `.pill--info` with the words
  "AI-only, verify". Confidence is a number (`0.92`), never a bar.
- **Dialogs** (review: accept/correct/reject) are the one place a shadow appears
  (`--shadow-float`); use `<dialog>` for focus trapping.
- **Focus:** a 2 px `--focus-edge` outline plus a sunflower halo, on every interactive element.

## States

- **Loading:** the final layout with flat `--surface-2` bars at each value's real size; no
  shimmer, no spinner in content, no layout shift when data lands.
- **Empty:** the block keeps its frame and header plus one sentence that names the next step
  ("No documents yet. Drop a PDF or scan here, or choose a file.").
- **Error:** inside the block that failed, one sentence with what failed and a Retry text button;
  the server's `detail` message shown as written.
- **Zero** prints as `0`; missing values are an em dash in `--muted`.
- **Offline mode** (AI off) is a mode, not an error: a grey dot and "Rules only" in the top bar.

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
