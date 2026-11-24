# Fingerprint test sub-project (`/test/`)

A private browser-fingerprint lab hosted inside the mcp-api.net site: open
<https://mcp-api.net/test/>, it computes a detailed fingerprint with CreepJS and stores every
run in MongoDB, so you can compare how your fingerprint changes across browsers, profiles,
VPNs, anti-detect setups, automation frameworks, etc.

It is **not linked** anywhere on the site, is `Disallow`ed in `/robots.txt`, and is sent with
`noindex` (meta tag + `X-Robots-Tag` header).

## How to use

1. Open `https://mcp-api.net/test/?tag=<behavior>` — e.g. `?tag=chrome-incognito`,
   `?tag=firefox-resistfp`, `?tag=playwright-stealth`, `?tag=brave-vpn-nl`.
2. Wait a few seconds: when CreepJS finishes, the bar at the bottom shows `saved ✓ id=…`.
3. Change one variable (browser flag, extension, network, automation…), keep or change the tag,
   reload. **save again** re-posts the current result without recomputing.

The tag input is remembered per browser (localStorage); `?tag=` overrides it.

## What gets stored

MongoDB cluster from `MONGODB_URI` (same as invoices), **separate database** `fingerprints`
(override with `FP_DB_NAME`), collection `fp_tests`. One document per run:

| field | content |
|---|---|
| `received_at` | UTC time |
| `tag` | your label |
| `ip` | client IP (via Caddy `X-Forwarded-For`) |
| `user_agent`, `headers` | request headers as `[name, value]` pairs (cookies dropped) |
| `fp_id` | CreepJS FP ID (hash of the stable subset) |
| `fuzzy` | CreepJS fuzzy hash — similar fingerprints share long prefixes |
| `computed_ms` | time until CreepJS finished |
| `fingerprint` | full `window.Fingerprint` (~250–300 KB): navigator, worker scope, canvas, WebGL, audio, fonts, screen, timezone/intl, CSS, math, DOMRect/SVG, voices, media, headless & stealth scores, `lies`, `resistance`, … |
| `creep` | `window.Creep`, the subset hashed into FP ID |

Indexes: `received_at`, `tag`, `fp_id`.

## Results & comparison page (`/test/results`)

Open <https://mcp-api.net/test/results> (also linked from the bar on `/test/`).

- **Stored runs**: enter `FP_TEST_TOKEN` (remembered in the browser), optionally a tag filter,
  **Load runs**. Tick 2 runs → **Compare selected** (first ticked = A), or 3+ → **Distance
  matrix** (weighted distance for every pair; click a cell to open that pair). **paste ↓** puts a
  run's full JSON into the next empty paste box.
- **Paste comparison**: paste any two fingerprints, either a stored run, the output of **copy JSON**
  on `/test/`, or a raw CreepJS `window.Fingerprint`. Comparison runs entirely in the browser, so
  pasted data never leaves it. `window.fpCompare` exposes `compare/normalize/flatten` for console use.

What the comparison shows:

| metric | meaning |
|---|---|
| Weighted distance | mean of component distances weighted by identifying power (canvas/WebGL 3, audio/fonts/DOMRect/screen/navigator/worker 2, most others 1, error bookkeeping ≤0.5) |
| Unweighted distance | plain mean of component distances |
| Components changed | components whose CreepJS `$hash` differs (x / 25) |
| Fuzzy bins differ | differing characters of the 64-char CreepJS fuzzy hash; each char hashes one bin of metrics |
| FP ID | same/different hash of the stable subset (components badged *in FP ID*) |
| Values changed | leaf values with distance > 0 |

**Component summary table** (also as CSV): one row per component with its **result**,
**comparison type** and counts. Click a row to jump to its details.

- *binary*: a single non-numeric value → `match` / `no match`
- *proportional*: several exact-match values → similarity = share of values that match
- *continuous*: contains lists or numbers → graded similarity (Jaccard / relative difference); shows
  how many of its values are graded vs exact-match

Result is similarity (100% = identical; tiny real differences show as `>99.99%`, never rounded to 100%).
Columns also include values changed, `$hash` match, weight, *in FP ID*, and *lied* flags.

**Raw values table**: every flattened value (`component`, `path`, A, B, per-value distance), with a
component filter, text search, *only differences*, *show more* paging, click-to-copy of the full value
(data URIs, long lists), and CSV export. Works for a single fingerprint too: **raw** on a stored run,
or **Raw values only** with one paste box filled.

**Component distances**: per component a distance bar, the badges *in FP ID*, *hash ≠/=*, *lied: A/B*, *missing*, and on
click an explanation of what the component measures plus every changed value (A vs B, with a
per-value distance; lists show added/removed items).

Leaf distances: lists of values → Jaccard distance; numbers → relative difference
`|a−b| / max(|a|,|b|)` capped at 1; strings/booleans/data URIs → 0 or 1; missing on one side → 1.
Component distance = mean of its leaf distances.

The data API behind the page (token as `X-FP-Token` header or `?token=`; 404 without a valid
token or when `FP_TEST_TOKEN` is unset on the server):

- `GET /test/api/results?[tag=…][&limit=100]`: summaries, newest first
- `GET /test/api/results/{id}`: full document

Or query Mongo directly:

```js
use fingerprints
db.fp_tests.find({}, {fingerprint: 0, creep: 0, headers: 0}).sort({received_at: -1}).limit(20)
// which tags produced which FP IDs
db.fp_tests.aggregate([{$group: {_id: {tag: "$tag", fp: "$fp_id"}, n: {$sum: 1}}}])
// lies detected per run
db.fp_tests.find({}, {tag: 1, "fingerprint.lies.totalLies": 1, "fingerprint.headless": 1})
```

## Code map

| path | role |
|---|---|
| `app/creepjs/creep.js`, `style.min.css`, `favicon.ico`, `LICENSE` | vendored CreepJS build (MIT), commit in `app/creepjs/VERSION` |
| `app/creepjs/index.html` | CreepJS page, adapted: collector bar, `noindex`, test sub-page links removed |
| `app/creepjs/collect.js` | waits for `window.Fingerprint`/`window.Creep`, POSTs to `/test/collect`; **copy JSON** button |
| `app/creepjs/results.html`, `results.js` | results list, pairwise comparison, distance matrix (client-side) |
| `app/fptest.py` | Mongo storage + results queries |
| `app/main.py` | `/robots.txt`, `/test` → `/test/` redirect, `/test/collect`, `/test/results` page, `/test/api/results*`, static mount at `/test` |

The page must live at `/test/` (trailing slash): `creep.js` registers itself as a service/shared
worker via the relative path `./creep.js`, so assets are mounted under `/test/` too.

## Limits / caveats

- **No TLS / HTTP2 fingerprints** (JA3/JA4, Akamai h2): Caddy terminates TLS before the app.
  For that, run something like `pagpeter/TrackMe` on its own subdomain with TLS passthrough.
- Header order is as forwarded by Caddy, not necessarily what the browser sent.
- `/test/collect` is unauthenticated (anyone who finds it can add rows); payloads are capped at
  4 MB. Tag your own runs so you can filter.
- WebRTC section uses Google STUN servers (as upstream CreepJS does); the WebRTC/IP data is
  shown on the page but is not part of `window.Fingerprint`.

## Updating CreepJS

```bash
git clone --depth 1 https://github.com/abrahamjuliot/creepjs /tmp/creepjs
cp /tmp/creepjs/docs/creep.js /tmp/creepjs/docs/style.min.css app/creepjs/
git -C /tmp/creepjs rev-parse HEAD > app/creepjs/VERSION
```

Then reload `/test/` locally and check that the bar reaches `saved ✓`. If upstream renamed the
`.fingerprint-header` element or the `window.Fingerprint`/`window.Creep` globals, adjust
`collect.js`.
