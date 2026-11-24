// Results list + fingerprint comparison for /test/results.
// All comparison happens client-side; the API is only used to list/fetch stored runs.
(function () {
	'use strict'

	// ---------------------------------------------------------------- components
	// weight: rough identifying power (entropy x stability) used for the weighted distance.
	// inFp: part of window.Creep, i.e. hashed into the CreepJS FP ID.
	const COMPONENTS = {
		canvas2d: { label: 'Canvas 2D', weight: 3, inFp: true,
			explain: 'Images drawn with the 2D canvas API (text, emoji, gradients, CPU-forced paint) exported as data URIs, plus text-metric sums. Output depends on GPU, driver, OS font rasterizer and anti-aliasing, so it is highly identifying. Canvas-noise extensions and anti-detect browsers change these values, often on every load.' },
		canvasWebgl: { label: 'WebGL', weight: 3, inFp: true,
			explain: 'WebGL renderer/vendor strings (gpu), supported extensions, ~80 capability parameters, and pixels/images of a rendered scene. Reveals the GPU model and driver; spoofed renderer strings that do not match the rendered pixels are a classic lie signal.' },
		offlineAudioContext: { label: 'Audio', weight: 2, inFp: true,
			explain: 'An OfflineAudioContext renders an oscillator through a compressor; sums of the resulting samples, frequency and time-domain data are compared. Differences come from the audio stack, CPU and browser build. "noise" shows added randomization (Brave, anti-detect).' },
		fonts: { label: 'Fonts', weight: 2, inFp: true,
			explain: 'Fonts detected via FontFace loading, app-specific fonts (Office, Adobe…), emoji set and pixel-size sums. Reflects OS version and installed software; restricted by Firefox resistFingerprinting / Brave.' },
		clientRects: { label: 'DOMRect', weight: 2, inFp: false,
			explain: 'Sub-pixel sizes of elements and text ranges from getClientRects/getBoundingClientRect. Sensitive to font rendering, zoom level, device pixel ratio and OS scaling. Randomized by some privacy extensions.' },
		svg: { label: 'SVGRect', weight: 1, inFp: false,
			explain: 'SVG text measurements (bBox, char extents, text length). Same idea as DOMRect, through the SVG rendering path.' },
		screen: { label: 'Screen', weight: 2, inFp: true,
			explain: 'screen width/height, available area (taskbar/dock), color and pixel depth, touch support. Changes with monitor, OS scaling, window manager and spoofing.' },
		navigator: { label: 'Navigator', weight: 2, inFp: false,
			explain: 'navigator properties: userAgent, platform, languages, hardwareConcurrency, deviceMemory, doNotTrack/GPC, plugins, mimeTypes, permissions, userAgentData (client hints) and WebGPU. The usual target of UA spoofing.' },
		workerScope: { label: 'Worker scope', weight: 2, inFp: true,
			explain: 'The same navigator, locale, timezone and WebGL GPU values read inside a Web Worker. Spoofing that only patches the main window often forgets workers, so a mismatch with Navigator is a strong lie signal.' },
		voices: { label: 'Speech voices', weight: 1, inFp: false,
			explain: 'speechSynthesis voices (local and remote) and the default voice. Depends on the OS, its version and installed language packs.' },
		media: { label: 'Media', weight: 1, inFp: true,
			explain: 'Audio/video MIME types and codecs reported by canPlayType / MediaSource / MediaRecorder. Varies with browser build (proprietary codecs) and OS.' },
		css: { label: 'Computed style', weight: 1, inFp: true,
			explain: 'Keys of the computed style declaration (engine/version) and system colors/fonts (OS theme, accent colors).' },
		cssMedia: { label: 'CSS media', weight: 1, inFp: true,
			explain: 'CSS media features via @media and matchMedia: color scheme, reduced motion/contrast, pointer/hover, device size, color gamut, forced colors. Changes with OS settings and device.' },
		timezone: { label: 'Timezone', weight: 1, inFp: false,
			explain: 'Timezone name, offset, and a location measured from historical offset behavior. A timezone that disagrees with the IP or with the measured location suggests spoofing.' },
		intl: { label: 'Intl', weight: 1, inFp: false,
			explain: 'Output of Intl formatters (date/time, numbers, plurals, list and display names) and the resolved locale. Reflects language settings and ICU version.' },
		maths: { label: 'Math', weight: 1, inFp: false,
			explain: 'Results of many Math functions on edge-case inputs. Floating-point implementation differs by JS engine and sometimes CPU architecture; it rarely changes for the same browser build.' },
		features: { label: 'Features / version', weight: 1, inFp: false,
			explain: 'Browser version estimated from supported JS, CSS and window features. A version that disagrees with the userAgent indicates UA spoofing.' },
		windowFeatures: { label: 'Window keys', weight: 1, inFp: false,
			explain: 'Names of global window properties. Shows engine and version, and injected globals from extensions or automation tools (e.g. cdc_ keys, __playwright).' },
		htmlElementVersion: { label: 'HTMLElement keys', weight: 1, inFp: false,
			explain: 'Property names on the HTMLElement prototype; mostly reflects engine and version.' },
		headless: { label: 'Headless', weight: 1, inFp: false,
			explain: 'Heuristics for headless/automated browsers: "like headless" traits, hard headless signals, and stealth-plugin artifacts, with percentage ratings and a platform estimate.' },
		resistance: { label: 'Resistance', weight: 1, inFp: false,
			explain: 'Detected privacy protections: privacy browser (Brave, Tor, Firefox RFP…), security level, mode, and an extension hash pattern for blocker/spoofing extensions.' },
		lies: { label: 'Lies', weight: 1, inFp: false,
			explain: 'APIs whose prototypes or getters were tampered with (native-code checks, proxies, descriptor mismatches). Any entry means something is overriding browser APIs.' },
		consoleErrors: { label: 'Error messages', weight: 0.5, inFp: false,
			explain: 'Wording of native error messages for deliberately broken code. Specific to the JS engine and version.' },
		trash: { label: 'Trash', weight: 0.5, inFp: false,
			explain: 'Values CreepJS rejected as invalid or impossible (e.g. malformed GPU strings). Non-empty usually means spoofing.' },
		capturedErrors: { label: 'Captured errors', weight: 0.25, inFp: false,
			explain: 'Errors thrown while collecting. Mostly collection noise, but blocked APIs show up here too.' },
	}
	const DEFAULT_COMPONENT = { weight: 1, inFp: false, explain: 'Component not known to this page (newer CreepJS?). Compared generically.' }
	const compInfo = (key) => Object.assign({ label: key }, DEFAULT_COMPONENT, COMPONENTS[key] || {})

	// ---------------------------------------------------------------- helpers
	const $ = (id) => document.getElementById(id)
	const esc = (v) => String(v).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]))
	const pct = (x) => x > 0 && x < 0.0001 ? '<0.01%' : (x * 100).toFixed(x > 0 && x < 0.001 ? 2 : 1) + '%'
	const short = (s, n = 12) => (s ? String(s).slice(0, n) : '—')
	const storage = {
		get(k) { try { return localStorage.getItem(k) } catch (e) { return null } },
		set(k, v) { try { localStorage.setItem(k, v) } catch (e) { /* blocked */ } },
	}

	function preview(v, max = 140) {
		if (v === undefined) return '<span class="muted">(missing)</span>'
		if (v === null) return 'null'
		let s = typeof v === 'string' ? v : JSON.stringify(v)
		if (typeof v === 'string' && s.startsWith('data:')) {
			return esc(s.slice(0, 40)) + `… <span class="muted">(${s.length} chars, #${hashStr(s)})</span>`
		}
		if (s.length > max) return esc(s.slice(0, max)) + `… <span class="muted">(${s.length} chars)</span>`
		return esc(s)
	}

	function hashStr(s) { // tiny non-crypto hash, only to tell long strings apart visually
		let h = 2166136261
		for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619) }
		return (h >>> 0).toString(16).padStart(8, '0')
	}

	// ---------------------------------------------------------------- normalization
	function normalize(input, fallbackLabel) {
		let obj = input
		if (typeof input === 'string') {
			const txt = input.trim()
			if (!txt) throw new Error(`${fallbackLabel} is empty`)
			try { obj = JSON.parse(txt) } catch (e) { throw new Error(`${fallbackLabel} is not valid JSON: ${e.message}`) }
		}
		if (!obj || typeof obj !== 'object') throw new Error(`${fallbackLabel} is not an object`)
		let fp = obj.fingerprint || obj.Fingerprint
		if (!fp && (obj.navigator || obj.canvas2d || obj.workerScope)) fp = obj
		if (!fp || typeof fp !== 'object') throw new Error(`${fallbackLabel}: no fingerprint found (expected a "fingerprint" field or a raw CreepJS object)`)
		return {
			fp,
			meta: {
				label: fallbackLabel,
				id: obj.id || null,
				tag: obj.tag || null,
				time: obj.received_at || null,
				fp_id: obj.fp_id || null,
				fuzzy: obj.fuzzy || null,
				ip: obj.ip || null,
				ua: obj.user_agent || (fp.navigator && fp.navigator.userAgent) || null,
			},
		}
	}

	// ---------------------------------------------------------------- flatten + distances
	const isPrim = (v) => v === null || ['string', 'number', 'boolean'].includes(typeof v)

	function flatten(value, path, out) {
		if (Array.isArray(value)) {
			if (value.every(isPrim)) { out.set(path, { set: value }) ; return out }
			value.forEach((v, i) => flatten(v, `${path}[${i}]`, out))
			if (!value.length) out.set(path, { set: [] })
			return out
		}
		if (value && typeof value === 'object') {
			const keys = Object.keys(value).filter((k) => k !== '$hash')
			if (!keys.length) { out.set(path, { v: '{}' }); return out }
			for (const k of keys) flatten(value[k], path ? `${path}.${k}` : k, out)
			return out
		}
		out.set(path, { v: value })
		return out
	}

	function leafDistance(a, b) {
		if (!a || !b) return { d: 1 }
		if (a.set && b.set) {
			const A = new Set(a.set.map((x) => JSON.stringify(x)))
			const B = new Set(b.set.map((x) => JSON.stringify(x)))
			const added = [...B].filter((x) => !A.has(x))
			const removed = [...A].filter((x) => !B.has(x))
			const union = new Set([...A, ...B]).size
			const d = union ? (added.length + removed.length) / union : 0
			// same elements, different order — still a (tiny) difference worth surfacing
			const orderOnly = d === 0 && JSON.stringify(a.set) !== JSON.stringify(b.set)
			return { d, added, removed, orderOnly }
		}
		if (a.set || b.set) return { d: 1 }
		const x = a.v, y = b.v
		if (x === y) return { d: 0 }
		if (typeof x === 'number' && typeof y === 'number' && isFinite(x) && isFinite(y)) {
			const m = Math.max(Math.abs(x), Math.abs(y))
			return { d: m ? Math.min(1, Math.abs(x - y) / m) : 0 }
		}
		return { d: 1 }
	}

	function compareComponent(a, b) {
		const fa = a === undefined ? new Map() : flatten(a, '', new Map())
		const fb = b === undefined ? new Map() : flatten(b, '', new Map())
		const paths = [...new Set([...fa.keys(), ...fb.keys()])]
		const leaves = []
		let sum = 0
		for (const p of paths) {
			const la = fa.get(p), lb = fb.get(p)
			const r = leafDistance(la, lb)
			sum += r.d
			if (r.d > 0 || r.orderOnly) leaves.push(Object.assign({ path: p || '(value)', a: la, b: lb }, r))
		}
		leaves.sort((x, y) => y.d - x.d || x.path.localeCompare(y.path))
		const hashA = a && a.$hash, hashB = b && b.$hash
		// comparison mode: binary (one exact-match value), proportional (several), continuous (lists/numbers)
		const isGraded = (l) => !!l && (l.set !== undefined || typeof l.v === 'number')
		const gradedCount = paths.filter((p) => isGraded(fa.get(p)) || isGraded(fb.get(p))).length
		const mode = gradedCount ? 'continuous' : paths.length > 1 ? 'proportional' : 'binary'
		return {
			mode, gradedCount,
			distance: paths.length ? sum / paths.length : 0,
			total: paths.length,
			changed: leaves.filter((l) => l.d > 0).length,
			leaves,
			hashSame: hashA && hashB ? hashA === hashB : null,
			lied: { a: !!(a && a.lied), b: !!(b && b.lied) },
			missing: a === undefined ? 'a' : b === undefined ? 'b' : null,
		}
	}

	function fuzzyDistance(x, y) {
		if (!x || !y || x.length !== y.length) return null
		let diff = 0
		for (let i = 0; i < x.length; i++) if (x[i] !== y[i]) diff++
		return { diff, total: x.length }
	}

	function compare(A, B) {
		const keys = [...new Set([...Object.keys(A.fp), ...Object.keys(B.fp)])]
		const comps = keys.map((key) => Object.assign({ key, info: compInfo(key) }, compareComponent(A.fp[key], B.fp[key])))
		let wSum = 0, wTot = 0, uSum = 0, leavesChanged = 0, leavesTotal = 0, hashDiff = 0, hashKnown = 0
		for (const c of comps) {
			wSum += c.distance * c.info.weight; wTot += c.info.weight
			uSum += c.distance
			leavesChanged += c.changed; leavesTotal += c.total
			if (c.hashSame !== null) { hashKnown++; if (!c.hashSame) hashDiff++ }
		}
		return {
			comps,
			weighted: wTot ? wSum / wTot : 0,
			unweighted: comps.length ? uSum / comps.length : 0,
			leavesChanged, leavesTotal, hashDiff, hashKnown,
			componentsChanged: comps.filter((c) => c.changed > 0).length,
			fuzzy: fuzzyDistance(A.meta.fuzzy, B.meta.fuzzy),
			fpIdSame: A.meta.fp_id && B.meta.fp_id ? A.meta.fp_id === B.meta.fp_id : null,
		}
	}

	// ---------------------------------------------------------------- rendering: comparison
	let current = null // { A, B, result }

	function renderComparison(A, B) {
		const result = compare(A, B)
		current = { A, B, result }
		$('result-card').classList.remove('hidden')
		const lbl = (m) => [m.label, m.tag && `tag=${m.tag}`, m.time && new Date(m.time).toLocaleString(), m.id && `id=${m.id}`].filter(Boolean).join(' · ')
		$('ab-labels').innerHTML = `A: ${esc(lbl(A.meta))}<br>B: ${esc(lbl(B.meta))}`

		const tiles = [
			{ v: pct(result.weighted), l: 'Weighted distance', h: 'components weighted by identifying power' },
			{ v: pct(result.unweighted), l: 'Unweighted distance', h: 'plain mean of component distances' },
			{ v: `${result.hashDiff} / ${result.hashKnown}`, l: 'Components changed', h: 'CreepJS component $hash differs' },
			result.fuzzy ? { v: `${result.fuzzy.diff} / ${result.fuzzy.total}`, l: 'Fuzzy bins differ', h: `${pct(result.fuzzy.diff / result.fuzzy.total)} of fuzzy hash` }
				: { v: '—', l: 'Fuzzy bins differ', h: 'fuzzy hash missing on one side' },
			{ v: result.fpIdSame === null ? '—' : result.fpIdSame ? '<span class="same">same</span>' : '<span class="diff">different</span>', l: 'FP ID', h: result.fpIdSame === null ? 'FP ID missing on one side' : 'hash of the stable subset', raw: true },
			{ v: `${result.leavesChanged} / ${result.leavesTotal}`, l: 'Values changed', h: 'leaf values with distance > 0' },
		]
		$('tiles').innerHTML = tiles.map((t) => `<div class="tile"><div class="v">${t.raw ? t.v : esc(t.v)}</div><div class="l">${esc(t.l)}</div><div class="h">${esc(t.h)}</div></div>`).join('')
		renderComponents()
		renderSummary()
		showRaw(A, B)
		$('result-card').scrollIntoView({ behavior: 'smooth', block: 'start' })
	}

	function renderComponents() {
		if (!current) return
		const onlyChanged = $('only-changed').checked
		const sort = $('sort').value
		const totalWeight = current.result.comps.reduce((s, c) => s + c.info.weight, 0)
		let comps = current.result.comps.slice()
		if (onlyChanged) comps = comps.filter((c) => c.leaves.length || c.hashSame === false)
		comps.sort((x, y) => {
			if (sort === 'name') return x.info.label.localeCompare(y.info.label)
			if (sort === 'weighted') return y.distance * y.info.weight - x.distance * x.info.weight
			return y.distance - x.distance || x.info.label.localeCompare(y.info.label)
		})
		if (!comps.length) {
			$('components').innerHTML = '<p class="muted">No differences — the two fingerprints are identical in every component.</p>'
			return
		}
		$('components').innerHTML = comps.map((c) => {
			const impact = totalWeight ? (c.distance * c.info.weight) / totalWeight : 0
			const badges = [
				c.info.inFp ? '<span class="badge">in FP ID</span>' : '',
				c.hashSame === false ? '<span class="badge diff">hash ≠</span>' : c.hashSame ? '<span class="badge same">hash =</span>' : '',
				c.lied.a || c.lied.b ? `<span class="badge diff">lied: ${[c.lied.a && 'A', c.lied.b && 'B'].filter(Boolean).join(', ')}</span>` : '',
				c.missing ? `<span class="badge diff">missing in ${c.missing.toUpperCase()}</span>` : '',
			].join('')
			return `<div class="comp" data-key="${esc(c.key)}">
				<div class="comp-head" data-tip="${esc(`${c.info.label}: distance ${pct(c.distance)}, ${c.changed} of ${c.total} values changed, weight ${c.info.weight}, adds ${pct(impact)} to the weighted distance`)}">
					<div><span class="comp-name">${esc(c.info.label)}</span>${badges}</div>
					<div class="track"><div class="fill" style="width:${Math.max(c.distance > 0 ? 0.5 : 0, c.distance * 100)}%"></div></div>
					<div class="pct">${pct(c.distance)}</div>
					<div class="meta">${c.changed}/${c.total} values · w ${c.info.weight}</div>
				</div>
				<div class="comp-body"></div>
			</div>`
		}).join('')
	}

	function renderLeaves(c) {
		const rows = c.leaves.slice(0, 400).map((l) => {
			let a, b
			if (l.added || l.removed) {
				const fmt = (arr, cls) => arr.slice(0, 200).map((x) => `<span class="${cls}">${preview(JSON.parse(x), 80)}</span>`).join('') + (arr.length > 200 ? ` <span class="muted">+${arr.length - 200} more</span>` : '')
				a = l.removed.length ? fmt(l.removed, 'set-del') : '<span class="muted">—</span>'
				b = l.added.length ? fmt(l.added, 'set-add') : '<span class="muted">—</span>'
				if (l.orderOnly) { a = '<span class="muted">same items, different order</span>'; b = a }
				const common = l.a && l.b ? l.a.set.length - l.removed.length : 0
				b += ` <span class="muted">(${common} shared)</span>`
			} else {
				a = preview(l.a ? (l.a.set || l.a.v) : undefined)
				b = preview(l.b ? (l.b.set || l.b.v) : undefined)
			}
			return `<tr><td class="path">${esc(l.path)}</td><td>${a}</td><td>${b}</td><td class="d">${pct(l.d)}</td></tr>`
		}).join('')
		const more = c.leaves.length > 400 ? `<p class="muted">${c.leaves.length - 400} more changed values not shown.</p>` : ''
		return `<p class="explain">${esc(c.info.explain)}</p>` +
			(c.leaves.length
				? `<div class="legend"><span><span class="set-del">only in A</span></span><span><span class="set-add">only in B</span></span><span>distance per value, 0–100%</span></div>
				   <div class="table-wrap"><table class="leaves"><thead><tr><th>value</th><th>A</th><th>B</th><th>dist</th></tr></thead><tbody>${rows}</tbody></table></div>${more}`
				: '<p class="muted">All values equal (only the component hash differs, e.g. through fields excluded here like $hash ordering).</p>')
	}

	$('components').addEventListener('click', (e) => {
		const head = e.target.closest('.comp-head')
		if (!head || !current) return
		const el = head.parentElement
		const c = current.result.comps.find((x) => x.key === el.dataset.key)
		if (!el.classList.contains('open') && c) el.querySelector('.comp-body').innerHTML = renderLeaves(c)
		el.classList.toggle('open')
	})
	$('only-changed').addEventListener('change', renderComponents)
	$('sort').addEventListener('change', () => { renderComponents(); renderSummary() })

	// ---------------------------------------------------------------- component summary table
	const firstSentence = (t) => (t.match(/^.*?[.!?](\s|$)/) || [t])[0].trim()

	function summaryRows() {
		if (!current) return []
		const sort = $('sort').value
		const rows = current.result.comps.slice()
		rows.sort((x, y) => {
			if (sort === 'name') return x.info.label.localeCompare(y.info.label)
			if (sort === 'weighted') return y.distance * y.info.weight - x.distance * x.info.weight
			return y.distance - x.distance || x.info.label.localeCompare(y.info.label)
		})
		return rows.map((c) => {
			const sim = 1 - c.distance
			const match = c.changed === 0 && !c.missing
			return {
				c, sim, match,
				key: c.key, label: c.info.label, what: firstSentence(c.info.explain), mode: c.mode,
				hash: c.hashSame === null ? '' : c.hashSame ? 'match' : 'differs',
				result: c.mode === 'binary' ? (match ? 'match' : 'no match') : simText(sim),
				graded: c.gradedCount, exact: c.total - c.gradedCount,
				changed: c.changed, total: c.total, weight: c.info.weight, inFp: c.info.inFp,
				lied: [c.lied.a && 'A', c.lied.b && 'B'].filter(Boolean).join(' '),
			}
		})
	}

	// never round a real difference up to 100% or a real overlap down to 0%
	const simText = (sim) => sim >= 1 ? '100%' : sim > 0.9999 ? '>99.99%' : sim <= 0 ? '0%' : sim < 0.0001 ? '<0.01%' : (sim * 100).toFixed(2) + '%'

	function renderSummary() {
		const rows = summaryRows()
		$('comp-table').innerHTML = '<thead><tr><th>component</th><th>result</th><th>comparison</th><th class="num">values changed</th><th>$hash</th><th class="num">weight</th><th>in FP ID</th><th>lied</th><th>what it measures</th></tr></thead><tbody>' +
			rows.map((r) => {
				const result = r.mode === 'binary'
					? `<span class="pill ${r.match ? 'match' : 'nomatch'}">${r.match ? 'match' : 'no match'}</span>`
					: `<span class="mini"><i style="width:${(r.sim * 100).toFixed(1)}%"></i></span>${r.match ? '<span class="pill match">100%</span>' : esc(r.result)}`
				return `<tr data-key="${esc(r.key)}" data-tip="${esc(`${r.label}: ${r.mode} comparison, similarity ${simText(r.sim)}, ${r.changed}/${r.total} values changed. Click for details`)}">
					<td><b>${esc(r.label)}</b><div class="mono muted">${esc(r.key)}</div></td>
					<td class="num" style="text-align:left">${result}</td>
					<td>${esc(r.mode)}<div class="muted" style="font-size:11px;white-space:nowrap">${r.graded} graded · ${r.exact} exact</div></td>
					<td class="num">${r.changed} / ${r.total}</td>
					<td>${r.hash ? `<span class="${r.hash === 'match' ? 'same' : 'diff'}">${r.hash}</span>` : '<span class="muted">—</span>'}</td>
					<td class="num">${r.weight}</td>
					<td>${r.inFp ? 'yes' : ''}</td>
					<td>${r.lied ? `<span class="diff">${esc(r.lied)}</span>` : ''}</td>
					<td class="what">${esc(r.what)}</td>
				</tr>`
			}).join('') + '</tbody>'
	}

	$('comp-table').addEventListener('click', (e) => {
		const tr = e.target.closest('tr[data-key]')
		if (!tr) return
		$('only-changed').checked = false
		renderComponents()
		const el = document.querySelector(`.comp[data-key="${CSS.escape(tr.dataset.key)}"]`)
		if (!el) return
		if (!el.classList.contains('open')) el.querySelector('.comp-head').click()
		el.scrollIntoView({ behavior: 'smooth', block: 'start' })
	})

	function csvCell(v) {
		const s = v === undefined || v === null ? '' : typeof v === 'string' ? v : JSON.stringify(v)
		return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s
	}
	function download(name, rows) {
		const blob = new Blob(['﻿' + rows.map((r) => r.map(csvCell).join(',')).join('\r\n')], { type: 'text/csv;charset=utf-8' })
		const a = document.createElement('a')
		a.href = URL.createObjectURL(blob)
		a.download = name
		document.body.appendChild(a)
		a.click()
		a.remove()
		setTimeout(() => URL.revokeObjectURL(a.href), 1000)
	}
	const fileStem = () => ['fp', raw.A && (raw.A.meta.tag || raw.A.meta.id), raw.B && (raw.B.meta.tag || raw.B.meta.id)].filter(Boolean).join('_').replace(/[^\w.-]+/g, '-')

	$('dl-summary').addEventListener('click', () => {
		download(fileStem() + '_components.csv', [
			['component', 'key', 'comparison', 'graded_values', 'exact_values', 'similarity', 'result', 'values_changed', 'values_total', 'hash', 'weight', 'in_fp_id', 'lied', 'what_it_measures'],
			...summaryRows().map((r) => [r.label, r.key, r.mode, r.graded, r.exact, r.sim.toFixed(6), r.result, r.changed, r.total, r.hash, r.weight, r.inFp, r.lied, r.what]),
		])
	})

	// ---------------------------------------------------------------- raw values table
	const RAW_PAGE = 600
	let raw = { A: null, B: null, rows: [], shown: RAW_PAGE, visible: [] }
	const leafValue = (l) => (l === undefined ? undefined : l.set !== undefined ? l.set : l.v)

	function buildRawRows(A, B) {
		const keys = [...new Set([...Object.keys(A.fp), ...(B ? Object.keys(B.fp) : [])])]
		const rows = []
		for (const key of keys) {
			const fa = A.fp[key] === undefined ? new Map() : flatten(A.fp[key], '', new Map())
			const fb = !B ? null : B.fp[key] === undefined ? new Map() : flatten(B.fp[key], '', new Map())
			const paths = [...new Set([...fa.keys(), ...(fb ? fb.keys() : [])])]
			for (const p of paths) {
				const la = fa.get(p)
				const lb = fb ? fb.get(p) : undefined
				const d = fb ? leafDistance(la, lb).d : null
				rows.push({ key, label: compInfo(key).label, path: p || '(value)', a: leafValue(la), b: leafValue(lb), d })
			}
		}
		return rows
	}

	function showRaw(A, B) {
		raw = { A, B, rows: buildRawRows(A, B), shown: RAW_PAGE, visible: [] }
		const keys = [...new Set(raw.rows.map((r) => r.key))]
		const prev = $('raw-comp').value
		$('raw-comp').innerHTML = '<option value="">all components</option>' + keys.map((k) => `<option value="${esc(k)}">${esc(compInfo(k).label)}</option>`).join('')
		if (keys.includes(prev)) $('raw-comp').value = prev
		$('raw-diff-wrap').classList.toggle('hidden', !B)
		if (!B) $('raw-diff').checked = false
		$('raw-sub').textContent = B ? `A: ${A.meta.label} · B: ${B.meta.label}` : A.meta.label
		$('raw-card').classList.remove('hidden')
		renderRaw()
	}

	function filteredRaw() {
		const comp = $('raw-comp').value
		const q = $('raw-search').value.trim().toLowerCase()
		const onlyDiff = $('raw-diff').checked
		return raw.rows.filter((r) => {
			if (comp && r.key !== comp) return false
			if (onlyDiff && !(r.d > 0)) return false
			if (q) {
				const hay = (r.key + '.' + r.path + ' ' + JSON.stringify(r.a ?? '') + ' ' + JSON.stringify(r.b ?? '')).toLowerCase()
				if (!hay.includes(q)) return false
			}
			return true
		})
	}

	function renderRaw() {
		const two = !!raw.B
		const rows = filteredRaw()
		const shown = rows.slice(0, raw.shown)
		$('raw-count').textContent = `${rows.length} value(s)` + (rows.length > shown.length ? `, showing ${shown.length}` : '')
		$('raw-more').classList.toggle('hidden', rows.length <= shown.length)
		const cell = (v, i, side) => `<td class="v" data-i="${i}" data-side="${side}" title="click to copy">${preview(v, 200)}</td>`
		$('raw-table').innerHTML = `<thead><tr><th>component</th><th>path</th><th>${two ? 'A' : 'value'}</th>${two ? '<th>B</th><th>dist</th>' : ''}</tr></thead><tbody>` +
			shown.map((r, i) => `<tr class="${two && r.d > 0 ? 'changed' : ''}">
				<td class="comp-col">${esc(r.label)}</td>
				<td class="path">${esc(r.path)}</td>
				${cell(r.a, i, 'a')}
				${two ? cell(r.b, i, 'b') + `<td class="d">${r.d > 0 ? pct(r.d) : '<span class="muted">=</span>'}</td>` : ''}
			</tr>`).join('') + '</tbody>'
		raw.visible = shown
	}

	$('raw-table').addEventListener('click', async (e) => {
		const td = e.target.closest('td.v')
		if (!td) return
		const r = raw.visible[+td.dataset.i]
		if (!r) return
		const v = td.dataset.side === 'a' ? r.a : r.b
		const text = v === undefined ? '' : typeof v === 'string' ? v : JSON.stringify(v)
		try {
			await navigator.clipboard.writeText(text)
			$('raw-count').textContent = `copied ${r.key}.${r.path} (${text.length} chars)`
		} catch (err) {
			$('raw-count').textContent = 'copy failed: ' + (err.message || err)
		}
	})
	$('raw-comp').addEventListener('change', () => { raw.shown = RAW_PAGE; renderRaw() })
	$('raw-diff').addEventListener('change', () => { raw.shown = RAW_PAGE; renderRaw() })
	let rawTimer
	$('raw-search').addEventListener('input', () => { clearTimeout(rawTimer); rawTimer = setTimeout(() => { raw.shown = RAW_PAGE; renderRaw() }, 200) })
	$('raw-more').addEventListener('click', () => { raw.shown += RAW_PAGE; renderRaw() })
	$('dl-raw').addEventListener('click', () => {
		const two = !!raw.B
		download(fileStem() + '_raw.csv', [
			two ? ['component', 'path', 'A', 'B', 'distance'] : ['component', 'path', 'value'],
			...filteredRaw().map((r) => (two ? [r.key, r.path, r.a, r.b, r.d] : [r.key, r.path, r.a])),
		])
	})

	// ---------------------------------------------------------------- tooltip
	const tip = $('tooltip')
	document.addEventListener('mousemove', (e) => {
		const t = e.target.closest('[data-tip]')
		if (!t) { tip.style.display = 'none'; return }
		tip.textContent = t.dataset.tip
		tip.style.display = 'block'
		const x = Math.min(e.clientX + 14, window.innerWidth - tip.offsetWidth - 8)
		const y = Math.min(e.clientY + 14, window.innerHeight - tip.offsetHeight - 8)
		tip.style.left = x + 'px'; tip.style.top = y + 'px'
	})

	// ---------------------------------------------------------------- paste compare
	$('compare').addEventListener('click', () => {
		$('cmp-msg').textContent = ''
		try {
			renderComparison(normalize($('in-a').value, 'A'), normalize($('in-b').value, 'B'))
		} catch (e) {
			$('cmp-msg').textContent = e.message
		}
	})
	$('raw-only').addEventListener('click', () => {
		$('cmp-msg').textContent = ''
		try {
			const hasA = $('in-a').value.trim()
			const hasB = $('in-b').value.trim()
			if (!hasA && !hasB) throw new Error('paste a fingerprint into A or B first')
			const A = hasA ? normalize($('in-a').value, 'A') : normalize($('in-b').value, 'B')
			const B = hasA && hasB ? normalize($('in-b').value, 'B') : null
			showRaw(A, B)
			$('raw-card').scrollIntoView({ behavior: 'smooth', block: 'start' })
		} catch (e) {
			$('cmp-msg').textContent = e.message
		}
	})
	$('swap').addEventListener('click', () => { const a = $('in-a').value; $('in-a').value = $('in-b').value; $('in-b').value = a })
	$('clear').addEventListener('click', () => { $('in-a').value = ''; $('in-b').value = ''; $('cmp-msg').textContent = '' })

	// ---------------------------------------------------------------- stored runs
	$('token').value = storage.get('fp-token') || ''
	let runs = []
	const selected = [] // ids in selection order
	const fullCache = new Map()

	async function api(path) {
		const res = await fetch(path, { headers: { 'X-FP-Token': $('token').value.trim() }, cache: 'no-store' })
		if (res.status === 404) throw new Error('not found — wrong token, or FP_TEST_TOKEN not set on the server')
		if (!res.ok) throw new Error(`HTTP ${res.status}`)
		return res.json()
	}

	async function loadRuns() {
		storage.set('fp-token', $('token').value.trim())
		$('runs-msg').textContent = 'loading…'
		const q = new URLSearchParams({ limit: $('limit').value })
		if ($('tag-filter').value.trim()) q.set('tag', $('tag-filter').value.trim())
		try {
			runs = await api('/test/api/results?' + q)
			selected.length = 0
			$('runs-msg').textContent = `${runs.length} run(s)`
			$('runs').classList.remove('hidden')
			renderRuns()
		} catch (e) {
			$('runs-msg').textContent = e.message
		}
	}

	function renderRuns() {
		$('runs-body').innerHTML = runs.map((r) => {
			const n = selected.indexOf(r.id)
			return `<tr class="${n >= 0 ? 'sel' : ''}">
				<td><input type="checkbox" data-id="${esc(r.id)}" ${n >= 0 ? 'checked' : ''}> ${n >= 0 ? `<b>${n === 0 ? 'A' : n === 1 ? 'B' : n + 1}</b>` : ''}</td>
				<td class="mono">${esc(r.received_at ? new Date(r.received_at).toLocaleString() : '')}</td>
				<td>${esc(r.tag || '')}</td>
				<td class="mono" title="${esc(r.fp_id || '')}">${esc(short(r.fp_id))}</td>
				<td class="mono" title="${esc(r.fuzzy || '')}">${esc(short(r.fuzzy))}</td>
				<td class="mono">${esc(r.ip || '')}</td>
				<td class="ellipsis" title="${esc(r.user_agent || '')}">${esc(r.user_agent || '')}</td>
				<td style="white-space:nowrap"><button type="button" data-raw="${esc(r.id)}" title="Show all raw values of this run">raw</button> <button type="button" data-paste="${esc(r.id)}" title="Put this run's JSON into the next empty paste box">paste ↓</button></td>
			</tr>`
		}).join('')
		$('cmp-selected').disabled = selected.length !== 2
		$('matrix-selected').disabled = selected.length < 3
	}

	$('runs-body').addEventListener('change', (e) => {
		const id = e.target.dataset && e.target.dataset.id
		if (!id) return
		const i = selected.indexOf(id)
		if (e.target.checked && i < 0) selected.push(id)
		if (!e.target.checked && i >= 0) selected.splice(i, 1)
		renderRuns()
	})

	async function getFull(id) {
		if (!fullCache.has(id)) fullCache.set(id, await api('/test/api/results/' + encodeURIComponent(id)))
		return fullCache.get(id)
	}

	const runLabel = (doc) => doc.tag || short(doc.id, 8)

	$('runs-body').addEventListener('click', async (e) => {
		const rawId = e.target.dataset && e.target.dataset.raw
		if (rawId) {
			try {
				const doc = await getFull(rawId)
				showRaw(normalize(doc, `run ${runLabel(doc)}`), null)
				$('raw-card').scrollIntoView({ behavior: 'smooth', block: 'start' })
			} catch (err) {
				$('runs-msg').textContent = err.message
			}
			return
		}
		const id = e.target.dataset && e.target.dataset.paste
		if (!id) return
		try {
			const doc = await getFull(id)
			const box = !$('in-a').value.trim() ? $('in-a') : $('in-b')
			box.value = JSON.stringify(doc)
			$('cmp-msg').textContent = `run ${runLabel(doc)} pasted into ${box === $('in-a') ? 'A' : 'B'}`
		} catch (err) { $('runs-msg').textContent = err.message }
	})

	$('load').addEventListener('click', loadRuns)
	$('token').addEventListener('keydown', (e) => { if (e.key === 'Enter') loadRuns() })
	$('tag-filter').addEventListener('keydown', (e) => { if (e.key === 'Enter') loadRuns() })

	$('cmp-selected').addEventListener('click', async () => {
		$('runs-msg').textContent = 'fetching…'
		try {
			const [a, b] = await Promise.all(selected.slice(0, 2).map(getFull))
			$('runs-msg').textContent = ''
			renderComparison(normalize(a, `A (${runLabel(a)})`), normalize(b, `B (${runLabel(b)})`))
		} catch (e) { $('runs-msg').textContent = e.message }
	})

	// ---------------------------------------------------------------- matrix
	const SEQ = ['--seq-1', '--seq-2', '--seq-3', '--seq-4', '--seq-5', '--seq-6', '--seq-7']

	function seqStep(d, max) {
		if (d === 0) return { bg: 'var(--seq-0)', fg: 'var(--text-secondary)' }
		const i = Math.min(SEQ.length - 1, Math.floor((d / (max || 1)) * SEQ.length))
		const dark = matchMedia('(prefers-color-scheme: dark)').matches && document.documentElement.dataset.theme !== 'light'
		const lightText = dark ? i < 4 : i >= 3
		return { bg: `var(${SEQ[i]})`, fg: lightText ? '#fff' : '#0b0b0b' }
	}

	$('matrix-selected').addEventListener('click', async () => {
		$('runs-msg').textContent = 'fetching…'
		try {
			const docs = await Promise.all(selected.map(getFull))
			$('runs-msg').textContent = ''
			const norm = docs.map((d, i) => normalize(d, `${i + 1} (${runLabel(d)})`))
			const n = norm.length
			const m = Array.from({ length: n }, () => Array(n).fill(0))
			for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) m[i][j] = m[j][i] = compare(norm[i], norm[j]).weighted
			const max = Math.max(...m.flat(), 0.0001)
			const head = `<tr><th></th>${norm.map((x, i) => `<th class="mono" title="${esc(x.meta.tag || '')}">${i + 1}</th>`).join('')}</tr>`
			const body = norm.map((x, i) => `<tr><th class="rowh" title="${esc(x.meta.label)}">${i + 1}. ${esc(x.meta.tag || short(x.meta.id, 8))}</th>${m[i].map((d, j) => {
				if (i === j) return '<td class="cell muted">—</td>'
				const s = seqStep(d, max)
				return `<td class="cell" data-i="${i}" data-j="${j}" style="background:${s.bg};color:${s.fg}" data-tip="${esc(`${i + 1} ↔ ${j + 1}: weighted distance ${pct(d)} — click to compare`)}">${(d * 100).toFixed(1)}</td>`
			}).join('')}</tr>`).join('')
			$('matrix').innerHTML = head + body
			$('matrix').onclick = (e) => {
				const td = e.target.closest('td.cell[data-i]')
				if (td) renderComparison(norm[+td.dataset.i], norm[+td.dataset.j])
			}
			$('matrix-legend').innerHTML = `<span>values in % · color scale 0 → ${pct(max)} (max in this matrix)</span>` +
				[0, 0.25, 0.5, 0.75, 1].map((f) => { const s = seqStep(f * max, max); return `<span><span style="display:inline-block;width:14px;height:10px;border-radius:2px;background:${s.bg};vertical-align:middle"></span> ${pct(f * max)}</span>` }).join('')
			$('matrix-card').classList.remove('hidden')
			$('matrix-card').scrollIntoView({ behavior: 'smooth', block: 'start' })
		} catch (e) { $('runs-msg').textContent = e.message }
	})

	// expose for console use / debugging
	window.fpCompare = { compare, normalize, flatten }
})()
