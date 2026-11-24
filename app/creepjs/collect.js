// Collector for the /test fingerprint page.
// CreepJS exposes its results on window.Fingerprint (full) and window.Creep
// (the stable subset it hashes) when it finishes. We wait for them, let the
// fuzzy hash / FP ID render, then POST everything to /test/collect.
(function () {
	'use strict'
	const statusEl = document.getElementById('fp-status')
	const tagEl = document.getElementById('fp-tag')
	const resendEl = document.getElementById('fp-resend')
	const t0 = performance.now()

	const params = new URLSearchParams(location.search)
	let storedTag = ''
	try { storedTag = localStorage.getItem('fp-tag') || '' } catch (e) { /* storage blocked */ }
	tagEl.value = params.get('tag') || storedTag
	tagEl.addEventListener('change', () => {
		try { localStorage.setItem('fp-tag', tagEl.value) } catch (e) { /* storage blocked */ }
	})

	const setStatus = (msg) => { statusEl.textContent = msg }
	const headerHash = (label) => {
		const el = document.querySelector('.fingerprint-header')
		const m = el && el.innerText.match(new RegExp(label + ':\\s*([0-9a-f]{16,128})'))
		return m ? m[1] : null
	}

	async function send() {
		resendEl.disabled = true
		setStatus('saving…')
		const body = {
			tag: tagEl.value.trim() || null,
			page_url: location.href,
			referrer: document.referrer || null,
			computed_ms: Math.round(window.__fpReadyAt - t0),
			fp_id: headerHash('FP ID'),
			fuzzy: headerHash('Fuzzy'),
			fingerprint: window.Fingerprint,
			creep: window.Creep,
		}
		try {
			const res = await fetch('/test/collect', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(body),
				credentials: 'same-origin',
			})
			const data = await res.json().catch(() => ({}))
			if (!res.ok) throw new Error(data.detail || res.status)
			setStatus(`saved ✓ id=${data.id}` + (body.tag ? ` tag=${body.tag}` : ''))
		} catch (e) {
			setStatus(`save failed: ${e.message || e}`)
		} finally {
			resendEl.disabled = false
			copyEl.disabled = false
		}
	}
	resendEl.addEventListener('click', send)

	// copy the same payload (plus computed hashes) for the paste comparison on /test/results
	const copyEl = document.getElementById('fp-copy')
	copyEl.addEventListener('click', async () => {
		const doc = {
			tag: tagEl.value.trim() || null,
			received_at: new Date().toISOString(),
			fp_id: headerHash('FP ID'),
			fuzzy: headerHash('Fuzzy'),
			user_agent: navigator.userAgent,
			fingerprint: window.Fingerprint,
			creep: window.Creep,
		}
		try {
			await navigator.clipboard.writeText(JSON.stringify(doc))
			setStatus('copied JSON to clipboard')
		} catch (e) {
			setStatus('copy failed: ' + (e.message || e))
		}
	})

	const started = Date.now()
	const timer = setInterval(() => {
		if (window.Fingerprint && window.Creep) {
			clearInterval(timer)
			window.__fpReadyAt = performance.now()
			setStatus('fingerprint ready, finishing…')
			// give the fuzzy hash and FP ID a moment to render
			setTimeout(send, 2500)
		} else if (Date.now() - started > 90000) {
			clearInterval(timer)
			setStatus('timed out waiting for CreepJS (see console)')
		}
	}, 250)
})()
