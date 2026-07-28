<script lang="ts">
	/* One track lane: name, solo/mute, and a canvas-rendered peak waveform.
	   Peaks are computed once on the client from decoded audio (see
	   lib/peaks.ts) rather than round-tripping to the server for a picture. */
	interface Props {
		name: string;
		peaks: Float32Array | null;
		color: string;
		/** Optional pitch contour, 0..1 normalised, drawn over the waveform. */
		pitch?: Float32Array | null;
		playhead?: number | null; // 0..1
		loading?: boolean;
		empty?: string;
		height?: number;
		/** Supplying this makes the lane a drop target. Receives every dropped
		 *  file, so several takes can be added in one go. */
		onDropFile?: ((f: File[]) => void) | null;
		/** Shown on the right of the lane header (remove button, etc). */
		action?: import('svelte').Snippet | null;
		multiple?: boolean;
	}
	let {
		name,
		peaks,
		color,
		pitch = null,
		playhead = null,
		loading = false,
		empty = 'No audio loaded',
		height = 116,
		onDropFile = null,
		action = null,
		multiple = false
	}: Props = $props();

	// --- drag & drop -------------------------------------------------------
	let dragOver = $state(false);
	const droppable = $derived(!!onDropFile);

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
		const files = Array.from(e.dataTransfer?.files ?? []);
		if (files.length) onDropFile?.(files);
	}

	let canvas = $state<HTMLCanvasElement | null>(null);
	let wrap = $state<HTMLDivElement | null>(null);
	let fileInput = $state<HTMLInputElement | null>(null);

	/** Canvas 2D does NOT understand CSS custom properties — assigning
	 *  `ctx.fillStyle = 'var(--guide)'` is silently ignored and leaves the
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

		if (pitch && pitch.length) {
			ctx.strokeStyle = 'oklch(0.97 0.02 100)';
			ctx.lineWidth = 1.25;
			ctx.globalAlpha = 0.85;
			ctx.beginPath();
			let started = false;
			for (let x = 0; x < w; x++) {
				const i = Math.floor((x / w) * pitch.length);
				const v = pitch[i];
				if (!isFinite(v) || v < 0) {
					started = false;
					continue;
				}
				const y = h - v * h * 0.88 - h * 0.06;
				if (!started) {
					ctx.moveTo(x, y);
					started = true;
				} else ctx.lineTo(x, y);
			}
			ctx.stroke();
			ctx.globalAlpha = 1;
		}
	}

	$effect(() => {
		// Explicit reads so the effect re-runs when either buffer is replaced.
		const p = peaks;
		const pc = pitch;
		const h = height;
		void p;
		void pc;
		void h;
		draw();
		// Also redraw on resize — the first paint can happen while the lane
		// still has zero width (hidden tab, layout not settled), which would
		// otherwise leave the canvas blank until the next interaction.
		if (!wrap) return;
		const ro = new ResizeObserver(() => draw());
		ro.observe(wrap);
		return () => ro.disconnect();
	});
</script>

<div class="lane">
	<div class="lane-head">
		<span class="dot" style:background={color}></span>
		<span class="lane-name">{name}</span>
		{#if action}<span class="lane-action">{@render action()}</span>{/if}
	</div>

	<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
	<div
		class="canvas-wrap"
		class:droppable
		class:drag-over={dragOver}
		bind:this={wrap}
		style:height="{height}px"
		role={droppable ? 'button' : undefined}
		tabindex={droppable ? 0 : undefined}

		aria-label={droppable ? `Drop an audio file for ${name}` : undefined}
		ondragover={onDragOver}
		ondragleave={onDragLeave}
		ondrop={onDrop}
		onclick={() => droppable && fileInput?.click()}
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
				{multiple}
				onclick={(e) => e.stopPropagation()}
				onchange={(e) => {
					const el = e.currentTarget as HTMLInputElement;
					const files = Array.from(el.files ?? []);
					if (files.length) onDropFile?.(files);
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
	}
	.lane:last-child {
		border-bottom: 0;
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
	.lane-action {
		margin-left: auto;
		display: flex;
		align-items: center;
	}
	.lane-name {
		font-size: var(--t-micro);
		font-weight: 600;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: var(--ink-dim);
	}
	.canvas-wrap {
		position: relative;
		width: 100%;
		background: var(--surface-sunken);
		transition:
			background var(--fast) var(--ease),
			box-shadow var(--fast) var(--ease);
	}
	.canvas-wrap.droppable {
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
		background: linear-gradient(
			90deg,
			transparent,
			oklch(0.3 0.03 288 / 0.55),
			transparent
		);
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
