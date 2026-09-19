<script lang="ts">
	import { alignTakes, engineUp, type AlignResult, type Renderer } from '$lib/api';
	import Knob from '$lib/components/Knob.svelte';
	import Segmented from '$lib/components/Segmented.svelte';
	import Toggle from '$lib/components/Toggle.svelte';
	import WaveLane from '$lib/components/WaveLane.svelte';
	import { durationLabel, peaksFromBlob } from '$lib/peaks';
	import { zipAndDownload, type ZipEntry } from '$lib/zip';

	/** One dub take and everything derived from it. Kept as a list so a whole
	 *  stack (L + R doubles, ad-libs…) goes through in one pass — they all
	 *  align to the same guide, so there's no reason to do them one at a time. */
	interface Dub {
		id: number;
		file: File;
		peaks: Float32Array | null;
		loading: boolean;
		running: boolean;
		result: AlignResult | null;
		outPeaks: Float32Array | null;
		outUrl: string | null;
		error: string | null;
	}

	/** One guide track and the dubs aligned against it. A session per guide
	 *  track — verse guide, chorus guide, a different singer's guide — kept
	 *  as tabs, so switching between them doesn't mean re-loading anything. */
	interface Session {
		id: number;
		seq: number;
		guideFile: File | null;
		guidePeaks: Float32Array | null;
		guideLoading: boolean;
		dubs: Dub[];
		durationS: number;
	}

	let nextId = 0;
	let nextSessionSeq = 1;

	function makeSession(): Session {
		return {
			id: nextId++,
			seq: nextSessionSeq++,
			guideFile: null,
			guidePeaks: null,
			guideLoading: false,
			dubs: [],
			durationS: 0
		};
	}

	const initialSession = makeSession();
	let sessions = $state<Session[]>([initialSession]);
	let activeSessionId = $state(initialSession.id);
	const active = $derived(sessions.find((s) => s.id === activeSessionId)!);

	const sessionLabel = (s: Session) =>
		s.guideFile ? s.guideFile.name.replace(/\.[^.]+$/, '') : `Guide ${s.seq}`;
	const sessionDone = (s: Session) => s.dubs.filter((d) => d.result);

	function addSession() {
		const s = makeSession();
		sessions.push(s);
		activeSessionId = s.id;
	}

	function closeSession(id: number) {
		if (sessions.length <= 1) return; // always keep at least one tab
		const idx = sessions.findIndex((s) => s.id === id);
		if (idx === -1) return;
		for (const d of sessions[idx].dubs) if (d.outUrl) URL.revokeObjectURL(d.outUrl);
		sessions = sessions.filter((s) => s.id !== id);
		if (activeSessionId === id) {
			activeSessionId = (sessions[idx] ?? sessions[idx - 1] ?? sessions[0]).id;
		}
	}

	// Also doubles as each knob's double-click reset target.
	const DEFAULTS = { tightness: 0.85, maxShiftS: 0.4, pitchStrength: 0.5 };

	let matchTiming = $state(true);
	let tightness = $state(DEFAULTS.tightness);
	let maxShiftS = $state(DEFAULTS.maxShiftS);
	let matchPitch = $state(true);
	let pitchStrength = $state(DEFAULTS.pitchStrength);
	let nearestOctave = $state(true);
	let renderer = $state<Renderer>('praat');

	let running = $state(false);
	let error = $state<string | null>(null);
	let engineOnline = $state<boolean | null>(null);

	const done = $derived(sessionDone(active));
	const ready = $derived(!!active.guideFile && active.dubs.length > 0 && !running);
	const allDoneCount = $derived(sessions.reduce((n, s) => n + sessionDone(s).length, 0));

	$effect(() => {
		engineUp().then((v) => (engineOnline = v));
	});

	async function loadGuide(files: File[]) {
		const f = files[0];
		if (!f) return;
		const s = active;
		s.guideFile = f;
		s.guideLoading = true;
		error = null;
		try {
			s.guidePeaks = await peaksFromBlob(f);
			const ac = new AudioContext();
			try {
				s.durationS = (await ac.decodeAudioData(await f.arrayBuffer())).duration;
			} finally {
				void ac.close();
			}
		} catch {
			error = `Couldn't read ${f.name}. Is it a supported audio file?`;
			s.guideFile = null;
			s.guidePeaks = null;
		} finally {
			s.guideLoading = false;
		}
	}

	async function addDubs(files: File[]) {
		error = null;
		const s = active;
		for (const f of files) {
			const d: Dub = {
				id: nextId++,
				file: f,
				peaks: null,
				loading: true,
				running: false,
				result: null,
				outPeaks: null,
				outUrl: null,
				error: null
			};
			s.dubs.push(d);
			// Mutate through the array, NOT the `d` reference above: pushing
			// into a $state array stores a reactive proxy, and writing to the
			// original object bypasses it, so the lane never repaints.
			const live = s.dubs[s.dubs.length - 1];
			try {
				live.peaks = await peaksFromBlob(f);
			} catch {
				live.error = `Couldn't read ${f.name}.`;
			} finally {
				live.loading = false;
			}
		}
	}

	function removeDub(id: number) {
		const s = active;
		const d = s.dubs.find((x) => x.id === id);
		if (d?.outUrl) URL.revokeObjectURL(d.outUrl);
		s.dubs = s.dubs.filter((x) => x.id !== id);
	}

	async function run() {
		const s = active;
		if (!s.guideFile || !s.dubs.length) return;
		running = true;
		error = null;
		// Sequential, not parallel: each render is CPU-heavy and they all hit
		// one Python process — firing them at once would just thrash it. This
		// also covers switching tabs mid-run: `running` is shared across every
		// session, so the Align button stays disabled everywhere until this
		// session's queue finishes, and a second run can't start alongside it.
		for (const d of s.dubs) {
			d.running = true;
			d.error = null;
			try {
				const res = await alignTakes({
					guideFile: s.guideFile,
					guideName: s.guideFile.name,
					dubFile: d.file,
					dubName: d.file.name,
					tightness: matchTiming ? tightness : 0,
					maxShiftS,
					pitchStrength: matchPitch ? pitchStrength : 0,
					nearestOctave,
					renderer
				});
				d.result = res;
				if (d.outUrl) URL.revokeObjectURL(d.outUrl);
				d.outUrl = URL.createObjectURL(res.blob);
				d.outPeaks = await peaksFromBlob(res.blob);
				engineOnline = true;
			} catch (e) {
				d.error = e instanceof Error ? e.message : String(e);
			} finally {
				d.running = false;
			}
		}
		running = false;
	}

	const outName = (d: Dub) => d.file.name.replace(/\.[^.]+$/, '') + '_aligned.wav';

	function downloadOne(d: Dub) {
		if (!d.outUrl) return;
		const a = document.createElement('a');
		a.href = d.outUrl;
		a.download = outName(d);
		a.click();
	}

	function downloadTabZip() {
		const entries: ZipEntry[] = done.map((d) => ({ path: outName(d), blob: d.result!.blob }));
		void zipAndDownload(entries, `${sessionLabel(active)}_aligned.zip`);
	}

	function exportAllTabs() {
		const entries: ZipEntry[] = [];
		for (const s of sessions) {
			const label = sessionLabel(s);
			for (const d of sessionDone(s)) entries.push({ path: `${label}/${outName(d)}`, blob: d.result!.blob });
		}
		void zipAndDownload(entries, 'vocalign_export.zip');
	}

	const ticks = $derived.by(() => {
		const durationS = active.durationS;
		if (!durationS) return [] as number[];
		const step = [1, 2, 5, 10, 15, 30, 60].find((s) => s >= durationS / 8) ?? 60;
		const out: number[] = [];
		for (let t = step; t < durationS; t += step) out.push(t);
		return out;
	});
</script>

<div class="app">
	<header class="titlebar">
		<div class="brand">
			<span class="mark" aria-hidden="true"></span>
			<h1>vocalign</h1>
		</div>
		{#if engineOnline === false}
			<span class="pill pill-down">Engine offline</span>
		{:else if engineOnline}
			<span class="pill pill-up">Engine ready</span>
		{/if}
	</header>

	<main class="shell">
		<section class="stage" aria-label="Takes">
			<div class="tabbar" role="tablist" aria-label="Guide tracks">
				{#each sessions as s (s.id)}
					<div class="tab" class:active={s.id === activeSessionId}>
						<button
							type="button"
							role="tab"
							class="tab-select"
							aria-selected={s.id === activeSessionId}
							onclick={() => (activeSessionId = s.id)}
						>
							{sessionLabel(s)}
							{#if sessionDone(s).length}<span class="tab-count">{sessionDone(s).length}</span>{/if}
						</button>
						{#if sessions.length > 1}
							<button
								type="button"
								class="tab-x"
								aria-label="Close {sessionLabel(s)}"
								onclick={() => closeSession(s.id)}>✕</button
							>
						{/if}
					</div>
				{/each}
				<button type="button" class="tab-add" onclick={addSession}>+ Guide track</button>

				{#if allDoneCount > 0}
					<button type="button" class="tab-export" onclick={exportAllTabs}>
						Export all ({allDoneCount})
					</button>
				{/if}
			</div>

			<div class="ruler" aria-hidden="true">
				{#each ticks as t (t)}
					<span class="tick" style:left="{(t / active.durationS) * 100}%">{durationLabel(t)}</span>
				{/each}
			</div>

			<WaveLane
				name={active.guideFile ? `Guide — ${active.guideFile.name}` : 'Guide'}
				peaks={active.guidePeaks}
				color="var(--guide)"
				loading={active.guideLoading}
				empty="Drop the take you're matching to, or click to browse"
				onDropFile={loadGuide}
			/>

			{#each active.dubs as d (d.id)}
				<WaveLane
					name="Dub — {d.file.name}"
					peaks={d.peaks}
					color="var(--dub)"
					loading={d.loading}
					empty={d.error ?? 'Loading…'}
				>
					{#snippet action()}
						<button class="x" onclick={() => removeDub(d.id)} aria-label="Remove {d.file.name}"
							>✕</button
						>
					{/snippet}
				</WaveLane>

				{#if d.result || d.running}
					<WaveLane
						name="Aligned — {d.file.name}"
						peaks={d.outPeaks}
						color="var(--result)"
						loading={d.running}
						empty="Waiting…"
					/>
				{/if}
			{/each}

			<WaveLane
				name={active.dubs.length ? 'Add another dub' : 'Dub'}
				peaks={null}
				color="var(--dub)"
				empty={active.dubs.length
					? 'Drop more takes here'
					: 'Drop the take(s) to be aligned — several at once is fine'}
				height={active.dubs.length ? 62 : 116}
				multiple={true}
				onDropFile={addDubs}
			/>
		</section>

		<aside class="panel" aria-label="Controls">
			<p class="hint knob-hint">
				Drag to adjust · shift-drag to fine-tune · scroll to nudge · double-click to reset.
			</p>

			<div class="group">
				<div class="group-head">
					<span class="group-title">Match Timing</span>
					<Toggle bind:checked={matchTiming} label="Match timing" />
				</div>
				<Knob
					label="Max difference"
					bind:value={tightness}
					display="{Math.round(tightness * 100)} %"
					minLabel="Loose"
					maxLabel="Tight"
					accent="var(--dub)"
					disabled={!matchTiming}
					resetValue={DEFAULTS.tightness}
				/>
				<Knob
					label="Maximum shift"
					bind:value={maxShiftS}
					min={0.05}
					max={2}
					step={0.05}
					display="{Math.round(maxShiftS * 1000)} ms"
					minLabel="Tight"
					maxLabel="Wide"
					accent="var(--dub)"
					disabled={!matchTiming}
					resetValue={DEFAULTS.maxShiftS}
				/>
			</div>

			<div class="group">
				<div class="group-head">
					<span class="group-title">Match Pitch</span>
					<Toggle bind:checked={matchPitch} label="Match pitch" />
				</div>
				<Knob
					label="Pitch target"
					bind:value={pitchStrength}
					display="{Math.round(pitchStrength * 100)} %"
					minLabel="Dub"
					maxLabel="Guide"
					accent="var(--result)"
					disabled={!matchPitch}
					resetValue={DEFAULTS.pitchStrength}
				/>
				<Segmented
					label="Target mode"
					value={nearestOctave ? 'oct' : 'abs'}
					options={[
						{ value: 'oct', label: 'Nearest oct' },
						{ value: 'abs', label: 'Absolute' }
					]}
					disabled={!matchPitch}
				/>
				<p class="hint">
					50&nbsp;% is the sweet spot. On a wide stack, try switching this off — pitch variance
					between takes is a lot of what creates thickness.
				</p>
			</div>

			<div class="group">
				<span class="group-title">Engine</span>
				<Segmented
					label="Renderer"
					bind:value={renderer as string}
					options={[
						{ value: 'praat', label: 'Praat' },
						{ value: 'world', label: 'World' }
					]}
				/>
			</div>

			<div class="actions">
				<button class="go" onclick={run} disabled={!ready}>
					{#if running}
						<span class="spin" aria-hidden="true"></span>Aligning…
					{:else}
						Align{active.dubs.length > 1 ? ` ${active.dubs.length} dubs` : ''}
					{/if}
				</button>
				{#if !active.guideFile}
					<p class="hint">Load a guide take.</p>
				{:else if !active.dubs.length}
					<p class="hint">Add at least one dub.</p>
				{/if}
			</div>

			{#if error}<p class="error" role="alert">{error}</p>{/if}
			{#each active.dubs.filter((d) => d.error) as d (d.id)}
				<p class="error" role="alert">{d.file.name}: {d.error}</p>
			{/each}

			{#if done.length}
				<div class="result">
					<div class="res-head">
						<span class="group-title">Results — {sessionLabel(active)}</span>
						{#if done.length > 1}
							<button class="dl small" onclick={downloadTabZip}>Download tab (zip)</button>
						{/if}
					</div>

					{#each done as d (d.id)}
						<div class="res-item">
							<span class="res-name">{outName(d)}</span>
							<div class="metrics">
								<span><b>{d.result?.meanShiftMs.toFixed(0)}</b> ms drift</span>
								<span><b>{d.result?.channels === 1 ? 'mono' : `${d.result?.channels}ch`}</b></span>
							</div>
							<audio controls src={d.outUrl}></audio>
							<button class="dl" onclick={() => downloadOne(d)}>Download</button>
						</div>
					{/each}
					<p class="hint">44.1&nbsp;kHz. Drop each onto its own track, then pan.</p>
				</div>
			{/if}
		</aside>
	</main>
</div>

<style>
	.app {
		min-height: 100vh;
		display: flex;
		flex-direction: column;
		background: var(--bg);
	}
	.titlebar {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 11px 16px;
		border-bottom: 1px solid var(--line-soft);
		background: var(--surface);
	}
	.brand {
		display: flex;
		align-items: center;
		gap: 9px;
	}
	.mark {
		width: 13px;
		height: 13px;
		border-radius: 3px;
		background: linear-gradient(140deg, var(--guide), var(--result));
	}
	h1 {
		margin: 0;
		font-size: var(--t-body);
		font-weight: 600;
		letter-spacing: 0.02em;
	}
	.pill {
		font-size: var(--t-micro);
		font-weight: 600;
		letter-spacing: 0.05em;
		text-transform: uppercase;
		padding: 4px 9px;
		border-radius: 999px;
		border: 1px solid var(--line);
	}
	.pill-up {
		color: var(--ok);
		border-color: oklch(0.75 0.16 162 / 0.4);
	}
	.pill-down {
		color: var(--warn);
		border-color: oklch(0.8 0.14 78 / 0.4);
	}
	.shell {
		flex: 1;
		display: grid;
		grid-template-columns: minmax(0, 1fr) 268px;
		align-items: start;
		gap: 14px;
		padding: 14px;
	}
	.stage {
		background: var(--surface);
		border: 1px solid var(--line-soft);
		border-radius: var(--r-lg);
		overflow: hidden;
	}
	.tabbar {
		display: flex;
		align-items: center;
		gap: 6px;
		padding: 8px 10px;
		background: var(--surface-raised);
		border-bottom: 1px solid var(--line-soft);
		overflow-x: auto;
	}
	.tab {
		display: flex;
		align-items: center;
		flex: none;
		background: var(--surface-sunken);
		border: 1px solid var(--line-soft);
		border-radius: var(--r-sm);
		transition: border-color var(--fast) var(--ease);
	}
	.tab.active {
		border-color: var(--accent);
	}
	.tab-select {
		display: flex;
		align-items: center;
		gap: 6px;
		border: 0;
		background: transparent;
		color: var(--ink-muted);
		font-size: var(--t-micro);
		font-weight: 600;
		letter-spacing: 0.03em;
		padding: 7px 6px 7px 10px;
		white-space: nowrap;
		max-width: 160px;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.tab.active .tab-select {
		color: var(--ink);
	}
	.tab-count {
		font-family: var(--font-mono);
		font-size: 0.5625rem;
		color: var(--result);
		background: oklch(0.7 0.16 289 / 0.18);
		border-radius: 999px;
		padding: 1px 5px;
	}
	.tab-x {
		border: 0;
		background: transparent;
		color: var(--ink-faint);
		font-size: 0.65rem;
		line-height: 1;
		padding: 7px 9px 7px 3px;
		transition: color var(--fast) var(--ease);
	}
	.tab-x:hover {
		color: var(--ink);
	}
	.tab-add {
		flex: none;
		border: 1px dashed var(--line);
		background: transparent;
		color: var(--ink-muted);
		font-size: var(--t-micro);
		font-weight: 600;
		white-space: nowrap;
		padding: 7px 10px;
		border-radius: var(--r-sm);
		transition:
			color var(--fast) var(--ease),
			border-color var(--fast) var(--ease);
	}
	.tab-add:hover {
		color: var(--ink);
		border-color: var(--ink-faint);
	}
	.tab-export {
		margin-left: auto;
		flex: none;
		border: 1px solid var(--line);
		background: var(--surface-sunken);
		color: var(--result);
		font-size: var(--t-micro);
		font-weight: 600;
		white-space: nowrap;
		padding: 7px 10px;
		border-radius: var(--r-sm);
		transition:
			background var(--fast) var(--ease),
			border-color var(--fast) var(--ease);
	}
	.tab-export:hover {
		background: var(--surface-raised);
		border-color: var(--result);
	}
	.ruler {
		position: relative;
		height: 22px;
		background: var(--surface-raised);
		border-bottom: 1px solid var(--line-soft);
	}
	.tick {
		position: absolute;
		top: 5px;
		transform: translateX(-50%);
		font-family: var(--font-mono);
		font-size: 0.625rem;
		color: var(--ink-faint);
	}
	.tick::before {
		content: '';
		position: absolute;
		left: 50%;
		top: -5px;
		height: 5px;
		width: 1px;
		background: var(--line);
	}
	.x {
		border: 0;
		background: transparent;
		color: var(--ink-faint);
		font-size: 0.75rem;
		line-height: 1;
		padding: 4px 6px;
		border-radius: var(--r-sm);
		transition:
			color var(--fast) var(--ease),
			background var(--fast) var(--ease);
	}
	.x:hover {
		color: var(--ink);
		background: var(--surface-raised);
	}
	.panel {
		display: flex;
		flex-direction: column;
		gap: 14px;
		background: var(--surface);
		border: 1px solid var(--line-soft);
		border-radius: var(--r-lg);
		padding: 14px;
		position: sticky;
		top: 14px;
		max-height: calc(100vh - 28px);
		overflow-y: auto;
	}
	.group {
		display: flex;
		flex-direction: column;
		gap: 11px;
		padding-bottom: 14px;
		border-bottom: 1px solid var(--line-soft);
	}
	.group:last-of-type {
		border-bottom: 0;
		padding-bottom: 0;
	}
	.group-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
	}
	.group-title {
		font-size: var(--t-small);
		font-weight: 600;
		letter-spacing: 0.03em;
	}
	.hint {
		margin: 0;
		font-size: var(--t-micro);
		line-height: 1.45;
		color: var(--ink-muted);
	}
	.actions {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.go {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 8px;
		width: 100%;
		padding: 11px;
		border: 0;
		border-radius: var(--r-md);
		background: var(--accent);
		color: var(--accent-ink);
		font-size: var(--t-body);
		font-weight: 600;
		transition: background var(--fast) var(--ease);
	}
	.go:hover:not(:disabled) {
		background: var(--accent-hover);
	}
	.go:active:not(:disabled) {
		transform: translateY(1px);
	}
	.go:disabled {
		background: var(--surface-raised);
		color: var(--ink-faint);
	}
	.spin {
		width: 12px;
		height: 12px;
		border: 2px solid oklch(0.98 0.01 288 / 0.35);
		border-top-color: var(--accent-ink);
		border-radius: 50%;
		animation: spin 0.7s linear infinite;
	}
	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}
	.error {
		margin: 0;
		padding: 9px 11px;
		font-size: var(--t-micro);
		line-height: 1.5;
		color: oklch(0.85 0.09 22);
		background: oklch(0.68 0.19 22 / 0.12);
		border: 1px solid oklch(0.68 0.19 22 / 0.32);
		border-radius: var(--r-sm);
	}
	.result {
		display: flex;
		flex-direction: column;
		gap: 11px;
		padding-top: 14px;
		border-top: 1px solid var(--line-soft);
	}
	.res-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
	}
	.res-item {
		display: flex;
		flex-direction: column;
		gap: 6px;
		padding: 10px;
		background: var(--surface-sunken);
		border: 1px solid var(--line-soft);
		border-radius: var(--r-md);
	}
	.res-name {
		font-size: var(--t-micro);
		color: var(--ink);
		word-break: break-all;
	}
	.metrics {
		display: flex;
		gap: 10px;
		font-size: var(--t-micro);
		color: var(--ink-muted);
	}
	.metrics b {
		font-family: var(--font-mono);
		color: var(--ink);
		font-weight: 500;
	}
	audio {
		width: 100%;
		height: 30px;
	}
	.dl {
		padding: 7px;
		border: 1px solid var(--line);
		border-radius: var(--r-sm);
		background: transparent;
		color: var(--ink);
		font-size: var(--t-micro);
		transition: background var(--fast) var(--ease);
	}
	.dl:hover {
		background: var(--surface-raised);
	}
	.dl.small {
		padding: 4px 9px;
	}
	@media (max-width: 860px) {
		.shell {
			grid-template-columns: minmax(0, 1fr);
		}
		.panel {
			position: static;
			max-height: none;
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.spin {
			animation: none;
		}
	}
</style>
