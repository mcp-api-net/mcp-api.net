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

## Reading results

Either query Mongo directly, e.g.

```js
use fingerprints
db.fp_tests.find({}, {fingerprint: 0, creep: 0, headers: 0}).sort({received_at: -1}).limit(20)
// which tags produced which FP IDs
db.fp_tests.aggregate([{$group: {_id: {tag: "$tag", fp: "$fp_id"}, n: {$sum: 1}}}])
// lies detected per run
db.fp_tests.find({}, {tag: 1, "fingerprint.lies.totalLies": 1, "fingerprint.headless": 1})
```

or over HTTP, after setting `FP_TEST_TOKEN=<random>` in the server `.env` and redeploying:

- `GET /test/results?token=…[&tag=…][&limit=50]` — summaries (no big blobs), newest first
- `GET /test/results/{id}?token=…` — full document

Without `FP_TEST_TOKEN` both endpoints return 404.

## Code map

| path | role |
|---|---|
| `app/creepjs/creep.js`, `style.min.css`, `favicon.ico`, `LICENSE` | vendored CreepJS build (MIT), commit in `app/creepjs/VERSION` |
| `app/creepjs/index.html` | CreepJS page, adapted: collector bar, `noindex`, test sub-page links removed |
| `app/creepjs/collect.js` | waits for `window.Fingerprint`/`window.Creep`, POSTs to `/test/collect` |
| `app/fptest.py` | Mongo storage + results queries |
| `app/main.py` | `/robots.txt`, `/test` → `/test/` redirect, `/test/collect`, `/test/results*`, static mount at `/test` |

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
