<script lang="ts">
	/* One stem lane: name, solo/mute, a canvas peak waveform, and click-to-seek.
	   Peaks are computed on the client from the decoded buffer the player
	   already holds (lib/player.ts), rather than round-tripping to the server
	   for a picture of audio the browser has in memory. */
	interface Props {
		name: string;
		peaks: Float32Array | null;
		color: string;
		/** 0..1 across the lane; shared by every lane so they read as one ruler. */
		playhead?: number | null;
		loading?: boolean;
		empty?: string;
		height?: number;
		/** Supplying these turns on the solo/mute pair. */
		soloed?: boolean;
		muted?: boolean;
		onSolo?: (() => void) | null;
		onMute?: (() => void) | null;
		/** Fraction 0..1 of the lane width that was clicked. */
		onSeek?: ((frac: number) => void) | null;
		/** Supplying this makes the lane a drop target instead. */
		onDropFile?: ((f: File) => void) | null;
		action?: import('svelte').Snippet | null;
		/** Dimmed when another stem is soloed — the lane is loaded but silent. */
		silent?: boolean;
	}
	let {
		name,
		peaks,
		color,
		playhead = null,
		loading = false,
		empty = 'No audio loaded',
		height = 84,
		soloed = false,
		muted = false,
		onSolo = null,
		onMute = null,
		onSeek = null,
		onDropFile = null,
		action = null,
		silent = false
	}: Props = $props();

	// --- drag & drop -------------------------------------------------------
	let dragOver = $state(false);
	const droppable = $derived(!!onDropFile);
	const seekable = $derived(!!onSeek && !!peaks);

	function onDragOver(e: DragEvent) {
		if (!droppable) return;
		e.preventDefault(); // required, or the browser just opens the file
		dragOver = true;
	}
	function onDragLeave(e: DragEvent) {
		// Ignore the events fired while moving over child elements.
		if (e.currentTarget === e.target) dragOver = false;
	}
	function onDrop(e: DragEvent) {
		if (!droppable) return;
		e.preventDefault();
		dragOver = false;
		const file = e.dataTransfer?.files?.[0];
		if (file) onDropFile?.(file);
	}

	let canvas = $state<HTMLCanvasElement | null>(null);
	let wrap = $state<HTMLDivElement | null>(null);
	let fileInput = $state<HTMLInputElement | null>(null);

	function onLaneClick(e: MouseEvent) {
		if (droppable) {
			fileInput?.click();
			return;
		}
		if (!seekable || !wrap) return;
		const r = wrap.getBoundingClientRect();
		onSeek?.(Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)));
	}

	/** Canvas 2D does NOT understand CSS custom properties — assigning
	 *  `ctx.fillStyle = 'var(--vocals)'` is silently ignored and leaves the
	 *  fill at its default black, which is invisible on this background.
	 *  Resolve the variable to a real colour value first. */
	function resolveColor(c: string, el: HTMLElement): string {
		const m = c.match(/^var\((--[\w-]+)\)$/);
		if (!m) return c;
		const v = getComputedStyle(el).getPropertyValue(m[1]).trim();
		return v || '#ffffff';
	}

	function draw() {
		if (!canvas || !wrap || !peaks) return;
		const dpr = window.devicePixelRatio || 1;
		const w = wrap.clientWidth;
		const h = height;
		canvas.width = w * dpr;
		canvas.height = h * dpr;
		canvas.style.width = w + 'px';
		canvas.style.height = h + 'px';
		const ctx = canvas.getContext('2d');
		if (!ctx) return;
		ctx.scale(dpr, dpr);
		ctx.clearRect(0, 0, w, h);

		const mid = h / 2;
		const n = peaks.length;
		ctx.fillStyle = resolveColor(color, wrap);
		// One vertical bar per pixel column, mirrored around the centre —
		// reads as a solid filled waveform at a glance.
		for (let x = 0; x < w; x++) {
			const i = Math.floor((x / w) * n);
			const a = peaks[i] ?? 0;
			const barH = Math.max(1, a * (h * 0.44));
			ctx.fillRect(x, mid - barH, 1, barH * 2);
		}
	}

	$effect(() => {
		// Explicit reads so the effect re-runs when either changes.
		const p = peaks;
		const h = height;
		void p;
		void h;
		draw();
		// Also redraw on resize — the first paint can happen while the lane
		// still has zero width (layout not settled), which would otherwise
		// leave the canvas blank until the next interaction.
		if (!wrap) return;
		const ro = new ResizeObserver(() => draw());
		ro.observe(wrap);
		return () => ro.disconnect();
	});
</script>

<div class="lane" class:silent>
	<div class="lane-head">
		<span class="dot" style:background={color}></span>
		<span class="lane-name">{name}</span>
		{#if onSolo || onMute}
			<div class="sm">
				{#if onSolo}
					<button
						class="tog"
						class:on={soloed}
						aria-pressed={soloed}
						title="Solo {name}"
						onclick={onSolo}>S</button
					>
				{/if}
				{#if onMute}
					<button
						class="tog mute"
						class:on={muted}
						aria-pressed={muted}
						title="Mute {name}"
						onclick={onMute}>M</button
					>
				{/if}
			</div>
		{/if}
		{#if action}<span class="lane-action">{@render action()}</span>{/if}
	</div>

	<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
	<div
		class="canvas-wrap"
		class:droppable
		class:seekable
		class:drag-over={dragOver}
		bind:this={wrap}
		style:height="{height}px"
		role={droppable || seekable ? 'button' : undefined}
		tabindex={droppable || seekable ? 0 : undefined}
		aria-label={droppable ? `Drop an audio file for ${name}` : seekable ? `Seek in ${name}` : undefined}
		ondragover={onDragOver}
		ondragleave={onDragLeave}
		ondrop={onDrop}
		onclick={onLaneClick}
		onkeydown={(e) => {
			if (droppable && (e.key === 'Enter' || e.key === ' ')) {
				e.preventDefault();
				fileInput?.click();
			}
		}}
	>
		{#if droppable}
			<input
				class="hidden-input"
				bind:this={fileInput}
				type="file"
				accept="audio/*,video/*"
				onclick={(e) => e.stopPropagation()}
				onchange={(e) => {
					const el = e.currentTarget as HTMLInputElement;
					const f = el.files?.[0];
					if (f) onDropFile?.(f);
					el.value = '';
				}}
			/>
		{/if}
		{#if loading}
			<div class="state"><span class="shimmer"></span></div>
		{:else if !peaks}
			<div class="state"><span class="empty">{empty}</span></div>
		{/if}
		<canvas bind:this={canvas}></canvas>
		{#if playhead !== null}
			<div class="playhead" style:left="{playhead * 100}%"></div>
		{/if}
	</div>
</div>

<style>
	.lane {
		display: flex;
		flex-direction: column;
		border-bottom: 1px solid var(--line-soft);
		transition: opacity var(--fast) var(--ease);
	}
	.lane:last-child {
		border-bottom: 0;
	}
	/* Silenced by someone else's solo. Dimmed rather than hidden: you still
	   want to see the shape of what you're not currently hearing. */
	.lane.silent {
		opacity: 0.42;
	}
	.lane-head {
		display: flex;
		align-items: center;
		gap: 7px;
		padding: 7px 12px 5px;
	}
	.dot {
		width: 7px;
		height: 7px;
		border-radius: 2px;
		flex: none;
	}
	.lane-name {
		font-size: var(--t-micro);
		font-weight: 600;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: var(--ink-dim);
	}
	.sm {
		margin-left: auto;
		display: flex;
		gap: 3px;
	}
	.lane-action {
		display: flex;
		align-items: center;
	}
	.sm + .lane-action {
		margin-left: 6px;
	}
	.tog {
		border: 1px solid var(--line);
		background: var(--surface-sunken);
		color: var(--ink-faint);
		font-size: 0.625rem;
		font-weight: 700;
		line-height: 1;
		width: 20px;
		height: 18px;
		border-radius: 3px;
		transition:
			background var(--fast) var(--ease),
			color var(--fast) var(--ease),
			border-color var(--fast) var(--ease);
	}
	.tog:hover:not(.on) {
		color: var(--ink-dim);
		border-color: var(--ink-faint);
	}
	.tog.on {
		background: var(--warn);
		border-color: var(--warn);
		color: oklch(0.18 0.03 78);
	}
	.tog.mute.on {
		background: var(--danger);
		border-color: var(--danger);
		color: oklch(0.98 0.01 22);
	}
	.canvas-wrap {
		position: relative;
		width: 100%;
		background: var(--surface-sunken);
		transition:
			background var(--fast) var(--ease),
			box-shadow var(--fast) var(--ease);
	}
	.canvas-wrap.droppable,
	.canvas-wrap.seekable {
		cursor: pointer;
	}
	.canvas-wrap.droppable:hover {
		background: oklch(0.15 0.024 288);
	}
	.canvas-wrap.drag-over {
		background: oklch(0.2 0.05 288);
		box-shadow: inset 0 0 0 2px var(--accent);
	}
	.hidden-input {
		display: none;
	}
	canvas {
		display: block;
	}
	.state {
		position: absolute;
		inset: 0;
		display: grid;
		place-items: center;
	}
	.empty {
		font-size: var(--t-small);
		color: var(--ink-faint);
	}
	.shimmer {
		width: 100%;
		height: 100%;
		background: linear-gradient(90deg, transparent, oklch(0.3 0.03 288 / 0.55), transparent);
		background-size: 220% 100%;
		animation: sweep 1.15s linear infinite;
	}
	@keyframes sweep {
		to {
			background-position: -220% 0;
		}
	}
	.playhead {
		position: absolute;
		top: 0;
		bottom: 0;
		width: 1px;
		background: var(--ink);
		opacity: 0.75;
		pointer-events: none;
	}
	@media (prefers-reduced-motion: reduce) {
		.shimmer {
			animation: none;
			background: oklch(0.28 0.03 288 / 0.5);
		}
	}
</style>
