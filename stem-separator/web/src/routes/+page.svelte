<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import Segmented from '$lib/components/Segmented.svelte';
	import StemLane from '$lib/components/StemLane.svelte';
	import { peaksFromBlob, durationLabel } from '$lib/peaks';
	import { StemPlayer, peaksFromBuffer } from '$lib/player';
	import {
		cancelJob,
		fetchStem,
		health as getHealth,
		jobStatus,
		startSeparation,
		stemUrl,
		zipUrl,
		type Engine,
		type Health,
		type Job,
		type Mode
	} from '$lib/api';

	// --- engine / capabilities --------------------------------------------
	let health = $state<Health | null>(null);
	let engineOnline = $state<boolean | null>(null);

	// --- source track ------------------------------------------------------
	let sourceFile = $state<File | null>(null);
	let sourcePeaks = $state<Float32Array | null>(null);
	let sourceLoading = $state(false);

	// --- controls ----------------------------------------------------------
	let engine = $state<Engine>('demucs');
	let model = $state('htdemucs');
	let mode = $state<Mode>('four');
	// Demucs' shift-trick averaging. Exposed as three named steps rather than a
	// raw count: what you're actually choosing is how long you're willing to
	// wait, and 0/1/2 covers that range without pretending 7 is a useful answer.
	let quality = $state<'fast' | 'better' | 'best'>('fast');
	const SHIFTS = { fast: 0, better: 1, best: 2 } as const;

	// --- job ---------------------------------------------------------------
	let job = $state<Job | null>(null);
	let error = $state<string | null>(null);
	let polling = false;

	// --- stems / playback --------------------------------------------------
	interface Lane {
		name: string;
		label: string;
		color: string;
		peaks: Float32Array | null;
	}
	let lanes = $state<Lane[]>([]);
	let soloed = $state(new Set<string>());
	let muted = $state(new Set<string>());
	let playing = $state(false);
	let position = $state(0);
	let duration = $state(0);
	let loadingStems = $state(false);

	const player = new StemPlayer();
	let raf = 0;

	// Stem identity, in the order lanes should read top to bottom. Vocals first
	// because it's the stem you're almost always here for.
	const STEM_META: Record<string, { label: string; color: string }> = {
		vocals: { label: 'Vocals', color: 'var(--vocals)' },
		drums: { label: 'Drums', color: 'var(--drums)' },
		bass: { label: 'Bass', color: 'var(--bass)' },
		other: { label: 'Other', color: 'var(--other)' },
		no_vocals: { label: 'Instrumental', color: 'var(--instrumental)' }
	};

	const busy = $derived(job?.status === 'queued' || job?.status === 'running');
	const ready = $derived(!!sourceFile && !busy && engineOnline === true);
	const demucsMissing = $derived(engineOnline === true && health?.demucs === false);

	const modelInfo = $derived(health?.models.find((m) => m.id === model) ?? null);

	// --- setup -------------------------------------------------------------
	onMount(async () => {
		const h = await getHealth();
		health = h;
		engineOnline = !!h;
		if (h) {
			model = h.default_model;
			// Fall back to the engine that can actually run, rather than letting
			// someone configure a Demucs job that will be rejected on submit.
			if (!h.demucs) engine = 'quick';
		}
		tick();
	});

	onDestroy(() => {
		cancelAnimationFrame(raf);
		player.dispose();
	});

	/** One rAF loop drives every playhead — a timer per lane would let them
	 *  disagree by a frame, which on a shared ruler looks like drift. */
	function tick() {
		position = player.position();
		playing = player.playing;
		if (player.finished()) {
			player.pause();
			player.seek(0);
			position = 0;
			playing = false;
		}
		raf = requestAnimationFrame(tick);
	}

	// --- source ------------------------------------------------------------
	async function loadSource(file: File) {
		sourceFile = file;
		sourceLoading = true;
		error = null;
		resetStems();
		try {
			sourcePeaks = await peaksFromBlob(file);
		} catch {
			// Waveform only — the server decodes the real thing, and plenty of
			// formats the engine handles (m4a, video) won't decode in-browser.
			sourcePeaks = null;
		} finally {
			sourceLoading = false;
		}
	}

	function resetStems() {
		player.stop();
		lanes = [];
		soloed = new Set();
		muted = new Set();
		duration = 0;
		position = 0;
		if (job) void cancelJob(job.id);
		job = null;
	}

	// --- run ---------------------------------------------------------------
	async function run() {
		if (!sourceFile) return;
		error = null;
		lanes = [];
		try {
			job = await startSeparation({
				file: sourceFile,
				name: sourceFile.name,
				engine,
				model,
				mode,
				shifts: SHIFTS[quality]
			});
			void poll();
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
			job = null;
		}
	}

	async function poll() {
		if (polling || !job) return;
		polling = true;
		try {
			while (job && (job.status === 'queued' || job.status === 'running')) {
				await new Promise((r) => setTimeout(r, 500));
				if (!job) break;
				job = await jobStatus(job.id);
			}
			if (job?.status === 'done') await loadStems(job);
			else if (job?.status === 'error') error = job.error ?? 'Separation failed.';
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			polling = false;
		}
	}

	async function loadStems(j: Job) {
		loadingStems = true;
		// Lay the lanes out before the audio arrives so the shimmer appears in
		// the right shape — the wait is seconds on a long track.
		lanes = orderStems(j.stems).map((name) => ({
			name,
			label: STEM_META[name]?.label ?? name,
			color: STEM_META[name]?.color ?? 'var(--source)',
			peaks: null
		}));
		try {
			const blobs = await Promise.all(
				lanes.map(async (l) => ({ name: l.name, blob: await fetchStem(j.id, l.name) }))
			);
			const buffers = await player.load(blobs);
			lanes = lanes.map((l) => {
				const buf = buffers.get(l.name);
				return { ...l, peaks: buf ? peaksFromBuffer(buf) : null };
			});
			duration = player.duration;
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
			lanes = [];
		} finally {
			loadingStems = false;
		}
	}

	function orderStems(names: string[]): string[] {
		const order = Object.keys(STEM_META);
		return [...names].sort((a, b) => order.indexOf(a) - order.indexOf(b));
	}

	async function cancel() {
		if (!job) return;
		const id = job.id;
		job = null; // stops the poll loop
		await cancelJob(id);
	}

	// --- transport ---------------------------------------------------------
	function toggleSolo(name: string) {
		const next = new Set(soloed);
		next.has(name) ? next.delete(name) : next.add(name);
		soloed = next;
		player.applyMix(soloed, muted);
	}

	function toggleMute(name: string) {
		const next = new Set(muted);
		next.has(name) ? next.delete(name) : next.add(name);
		muted = next;
		player.applyMix(soloed, muted);
	}

	/** "Play just this one" — the question people actually arrive with. Solos
	 *  the stem and starts the transport in a single click, and stops on a
	 *  second click. Solo rather than mute-the-others so it composes with the
	 *  S/M buttons instead of fighting them. */
	async function soloPlay(name: string) {
		if (isPlayingAlone(name)) {
			player.pause();
			playing = false;
			return;
		}
		soloed = new Set([name]);
		player.applyMix(soloed, muted);
		if (!player.playing) await player.play();
		playing = player.playing;
	}

	function isPlayingAlone(name: string): boolean {
		return playing && soloed.size === 1 && soloed.has(name);
	}

	function clearMix() {
		soloed = new Set();
		muted = new Set();
		player.applyMix(soloed, muted);
	}

	async function togglePlay() {
		if (!lanes.length) return;
		if (player.playing) player.pause();
		else await player.play();
		playing = player.playing;
	}

	function seekFrac(frac: number) {
		if (!duration) return;
		player.seek(frac * duration);
		position = player.position();
	}

	function onKey(e: KeyboardEvent) {
		// Space is the universal transport key, but not while someone is in a
		// control — there it still means "activate this".
		const t = e.target as HTMLElement | null;
		if (t && ['INPUT', 'BUTTON', 'SELECT', 'TEXTAREA'].includes(t.tagName)) return;
		if (e.code === 'Space') {
			e.preventDefault();
			void togglePlay();
		}
	}

	function isSilent(name: string): boolean {
		return soloed.size > 0 ? !soloed.has(name) : muted.has(name);
	}

	const playFrac = $derived(duration > 0 ? position / duration : null);
	const outBase = $derived(sourceFile ? sourceFile.name.replace(/\.[^.]+$/, '') : 'track');
</script>

<svelte:window onkeydown={onKey} />

<div class="app">
	<header class="titlebar">
		<div class="brand">
			<span class="mark" aria-hidden="true"></span>
			<h1>stemsep</h1>
		</div>
		<div class="pills">
			{#if health?.device && health.demucs}
				<span class="pill">{health.device}</span>
			{/if}
			{#if engineOnline === false}
				<span class="pill pill-down">Engine offline</span>
			{:else if engineOnline}
				<span class="pill pill-up">Engine ready</span>
			{/if}
		</div>
	</header>

	<main class="shell">
		<section class="stage" aria-label="Tracks">
			<StemLane
				name={sourceFile ? `Source — ${sourceFile.name}` : 'Source'}
				peaks={sourcePeaks}
				color="var(--source)"
				height={sourceFile ? 72 : 116}
				loading={sourceLoading}
				empty="Drop a mix here, or click to browse"
				onDropFile={loadSource}
				onSeek={lanes.length ? seekFrac : null}
				playhead={lanes.length ? playFrac : null}
			>
				{#snippet action()}
					{#if sourceFile}
						<button class="x" onclick={resetStems} aria-label="Clear stems">Clear</button>
					{/if}
				{/snippet}
			</StemLane>

			{#each lanes as lane (lane.name)}
				<StemLane
					name={lane.label}
					peaks={lane.peaks}
					color={lane.color}
					loading={loadingStems && !lane.peaks}
					empty="Loading…"
					soloed={soloed.has(lane.name)}
					muted={muted.has(lane.name)}
					silent={isSilent(lane.name)}
					playhead={playFrac}
					onSolo={() => toggleSolo(lane.name)}
					onMute={() => toggleMute(lane.name)}
					onPlay={() => soloPlay(lane.name)}
					playingSolo={isPlayingAlone(lane.name)}
					onSeek={seekFrac}
				>
					{#snippet action()}
						<a
							class="x"
							href={stemUrl(job!.id, lane.name)}
							download="{outBase} - {lane.name}.wav"
							aria-label="Download {lane.label}">↓</a
						>
					{/snippet}
				</StemLane>
			{/each}

			{#if lanes.length}
				<div class="transport">
					<button class="play" onclick={togglePlay} aria-label={playing ? 'Pause' : 'Play'}>
						{#if playing}<span class="ico-pause"></span>{:else}<span class="ico-play"></span>{/if}
					</button>
					<span class="time">{durationLabel(position)} / {durationLabel(duration)}</span>
					{#if soloed.size || muted.size}
						<button class="x" onclick={clearMix}>Reset mix</button>
					{/if}
					<a class="dl" href={zipUrl(job!.id)} download="{outBase} - stems.zip">Download all</a>
				</div>
			{/if}
		</section>

		<aside class="panel" aria-label="Controls">
			<div class="group">
				<span class="group-title">Engine</span>
				<Segmented
					label="Engine"
					bind:value={engine as string}
					options={[
						{ value: 'demucs', label: 'Demucs' },
						{ value: 'quick', label: 'Quick' }
					]}
					disabled={busy}
				/>
				{#if engine === 'quick'}
					<p class="hint">
						No model, no wait — a repetition filter that pulls the vocal out of the mix. Expect
						burble and bleed. Fine as a guide track, not a release stem.
					</p>
				{:else if demucsMissing}
					<p class="warn-note">
						Demucs isn't installed in the API's environment. Run <code
							>pip install -r requirements.txt</code
						> (it pulls in PyTorch, ~2 GB), then restart the engine.
					</p>
				{/if}
			</div>

			{#if engine === 'demucs'}
				<div class="group">
					<span class="group-title">Stems</span>
					<Segmented
						label="Split into"
						bind:value={mode as string}
						options={[
							{ value: 'four', label: 'All four' },
							{ value: 'two', label: 'Vox / inst' }
						]}
						disabled={busy}
					/>
					<p class="hint">
						Four gives vocals, drums, bass and other. Two is the same model run with everything but
						the vocal summed — not faster, just fewer files.
					</p>
				</div>

				<div class="group">
					<span class="group-title">Model</span>
					<Segmented
						label="Model"
						bind:value={model}
						options={(health?.models ?? []).map((m) => ({ value: m.id, label: m.label }))}
						disabled={busy}
					/>
					{#if modelInfo}<p class="hint">{modelInfo.note}</p>{/if}
					<Segmented
						label="Quality"
						bind:value={quality as string}
						options={[
							{ value: 'fast', label: 'Fast' },
							{ value: 'better', label: 'Better' },
							{ value: 'best', label: 'Best' }
						]}
						disabled={busy}
					/>
					<p class="hint">
						Shift-trick averaging. Each step roughly doubles the time for a small gain — worth it on
						a final bounce, not while you're auditioning.
					</p>
				</div>
			{/if}

			<div class="actions">
				<button class="go" onclick={run} disabled={!ready || (engine === 'demucs' && demucsMissing)}>
					{#if busy}
						<span class="spin" aria-hidden="true"></span>Separating…
					{:else}
						Separate
					{/if}
				</button>

				{#if busy && job}
					<div class="prog">
						<div class="bar"><span style:width="{job.progress * 100}%"></span></div>
						<div class="prog-row">
							<span class="prog-msg">{job.message}</span>
							<span class="prog-pct">{Math.round(job.progress * 100)}%</span>
						</div>
						<button class="x" onclick={cancel}>Cancel</button>
					</div>
				{:else if !sourceFile}
					<p class="hint">Load a mix to separate.</p>
				{:else if job?.status === 'done'}
					<p class="hint">
						{job.stems.length} stems in {job.elapsed_s.toFixed(1)}s{job.device
							? ` on ${job.device}`
							: ''}. Solo them against each other before you commit.
					</p>
				{/if}
			</div>

			{#if error}<p class="error" role="alert">{error}</p>{/if}
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
		background: linear-gradient(140deg, var(--vocals), var(--bass), var(--other));
	}
	h1 {
		margin: 0;
		font-size: var(--t-body);
		font-weight: 600;
		letter-spacing: 0.02em;
	}
	.pills {
		display: flex;
		gap: 6px;
	}
	.pill {
		font-size: var(--t-micro);
		font-weight: 600;
		letter-spacing: 0.05em;
		text-transform: uppercase;
		padding: 4px 9px;
		border-radius: 999px;
		border: 1px solid var(--line);
		color: var(--ink-muted);
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
	.transport {
		display: flex;
		align-items: center;
		gap: 12px;
		padding: 9px 12px;
		border-top: 1px solid var(--line-soft);
		background: var(--surface-raised);
	}
	.play {
		width: 30px;
		height: 30px;
		flex: none;
		display: grid;
		place-items: center;
		border: 0;
		border-radius: 50%;
		background: var(--accent);
		color: var(--accent-ink);
		transition: background var(--fast) var(--ease);
	}
	.play:hover {
		background: var(--accent-hover);
	}
	/* Drawn rather than glyphs: ▶ and ❚❚ sit on different baselines and at
	   different optical weights across platforms, which makes the button jump
	   as it toggles. */
	.ico-play {
		width: 0;
		height: 0;
		border-left: 9px solid currentColor;
		border-top: 6px solid transparent;
		border-bottom: 6px solid transparent;
		margin-left: 3px;
	}
	.ico-pause {
		width: 9px;
		height: 11px;
		border-left: 3px solid currentColor;
		border-right: 3px solid currentColor;
	}
	.time {
		font-family: var(--font-mono);
		font-size: var(--t-small);
		color: var(--ink-dim);
		font-variant-numeric: tabular-nums;
	}
	.dl {
		margin-left: auto;
		font-size: var(--t-micro);
		font-weight: 600;
		letter-spacing: 0.05em;
		text-transform: uppercase;
		color: var(--ink-dim);
		text-decoration: none;
		border: 1px solid var(--line);
		padding: 6px 11px;
		border-radius: var(--r-sm);
		transition:
			color var(--fast) var(--ease),
			border-color var(--fast) var(--ease);
	}
	.dl:hover {
		color: var(--ink);
		border-color: var(--ink-faint);
	}
	.x {
		border: 0;
		background: transparent;
		color: var(--ink-faint);
		font-size: var(--t-micro);
		line-height: 1;
		padding: 4px 6px;
		border-radius: var(--r-sm);
		text-decoration: none;
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
	.warn-note {
		margin: 0;
		font-size: var(--t-micro);
		line-height: 1.5;
		color: var(--warn);
	}
	.warn-note code {
		font-family: var(--font-mono);
		font-size: 0.95em;
		color: var(--ink-dim);
	}
	.actions {
		display: flex;
		flex-direction: column;
		gap: 9px;
	}
	.go {
		border: 0;
		border-radius: var(--r-md);
		background: var(--accent);
		color: var(--accent-ink);
		font-size: var(--t-small);
		font-weight: 600;
		padding: 11px;
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 8px;
		transition: background var(--fast) var(--ease);
	}
	.go:hover:not(:disabled) {
		background: var(--accent-hover);
	}
	.go:disabled {
		background: var(--surface-raised);
		color: var(--ink-faint);
	}
	.spin {
		width: 12px;
		height: 12px;
		border: 2px solid currentColor;
		border-top-color: transparent;
		border-radius: 50%;
		animation: spin 0.7s linear infinite;
	}
	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}
	.prog {
		display: flex;
		flex-direction: column;
		gap: 6px;
	}
	.bar {
		height: 4px;
		background: var(--surface-sunken);
		border-radius: 999px;
		overflow: hidden;
	}
	.bar span {
		display: block;
		height: 100%;
		background: var(--accent);
		transition: width var(--med) var(--ease);
	}
	.prog-row {
		display: flex;
		justify-content: space-between;
		gap: 8px;
		font-size: var(--t-micro);
		color: var(--ink-muted);
	}
	.prog-pct {
		font-family: var(--font-mono);
		font-variant-numeric: tabular-nums;
	}
	.error {
		margin: 0;
		font-size: var(--t-micro);
		line-height: 1.5;
		color: var(--danger);
		white-space: pre-wrap;
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
</style>
