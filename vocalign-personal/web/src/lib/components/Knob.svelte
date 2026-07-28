<script lang="ts">
	/* Rotary knob — the standard affordance in every audio plugin, so it counts
	   as earned familiarity rather than a reinvented control. Backed by a real
	   <input type=range> so keyboard, screen readers and form semantics all
	   work; the visual is layered on top. */
	interface Props {
		label: string;
		value: number;
		min?: number;
		max?: number;
		step?: number;
		/** Text under the knob, e.g. "0 MS" or "48 %" */
		display: string;
		/** Labels flanking the arc, e.g. LOOSE / TIGHT */
		minLabel?: string;
		maxLabel?: string;
		accent?: string;
		disabled?: boolean;
	}
	let {
		label,
		value = $bindable(),
		min = 0,
		max = 1,
		step = 0.01,
		display,
		minLabel = '',
		maxLabel = '',
		accent = 'var(--guide)',
		disabled = false
	}: Props = $props();

	const SWEEP = 270; // degrees of travel, 8 o'clock → 4 o'clock
	const START = -135;

	const frac = $derived((value - min) / (max - min));
	const angle = $derived(START + frac * SWEEP);

	// Arc geometry for the filled indicator ring
	const R = 26;
	const C = 2 * Math.PI * R;
	const arcLen = $derived((SWEEP / 360) * C);
	const fillLen = $derived(frac * arcLen);

	let dragging = $state(false);

	function onPointerDown(e: PointerEvent) {
		if (disabled) return;
		dragging = true;
		(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
	}
	function onPointerMove(e: PointerEvent) {
		if (!dragging || disabled) return;
		// Vertical drag = the plugin convention; far more precise than
		// following the pointer angle around a small circle.
		const delta = -e.movementY / 180;
		value = Math.min(max, Math.max(min, value + delta * (max - min)));
	}
	function onPointerUp(e: PointerEvent) {
		dragging = false;
		(e.currentTarget as HTMLElement).releasePointerCapture?.(e.pointerId);
	}
</script>

<div class="knob-field" class:disabled>
	<span class="mlabel">{label}</span>

	<!-- The wrapper only adds pointer-drag as a convenience; the real control
	     is the <input type=range> inside it, which carries all the semantics.
	     Marked presentational so AT sees one control, not two. -->
	<div
		class="knob"
		class:dragging
		role="presentation"
		onpointerdown={onPointerDown}
		onpointermove={onPointerMove}
		onpointerup={onPointerUp}
		onpointercancel={onPointerUp}
	>
		<svg viewBox="0 0 64 64" aria-hidden="true">
			<!-- travel track -->
			<circle
				cx="32"
				cy="32"
				r={R}
				fill="none"
				stroke="var(--line)"
				stroke-width="3"
				stroke-linecap="round"
				stroke-dasharray="{arcLen} {C}"
				transform="rotate({START - 90} 32 32)"
			/>
			<!-- filled portion -->
			<circle
				cx="32"
				cy="32"
				r={R}
				fill="none"
				stroke={disabled ? 'var(--ink-faint)' : accent}
				stroke-width="3"
				stroke-linecap="round"
				stroke-dasharray="{fillLen} {C}"
				transform="rotate({START - 90} 32 32)"
			/>
			<circle cx="32" cy="32" r="19" fill="var(--surface-raised)" stroke="var(--line)" />
			<line
				x1="32"
				y1="32"
				x2="32"
				y2="17"
				stroke={disabled ? 'var(--ink-faint)' : accent}
				stroke-width="2.5"
				stroke-linecap="round"
				transform="rotate({angle} 32 32)"
			/>
		</svg>

		<input
			type="range"
			{min}
			{max}
			{step}
			bind:value
			{disabled}
			aria-label={label}
			aria-valuetext={display}
		/>
	</div>

	<div class="readout">
		{#if minLabel}<span class="edge">{minLabel}</span>{/if}
		<span class="value">{display}</span>
		{#if maxLabel}<span class="edge">{maxLabel}</span>{/if}
	</div>
</div>

<style>
	.knob-field {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 8px;
		padding: 12px 10px 10px;
		background: var(--surface-sunken);
		border: 1px solid var(--line-soft);
		border-radius: var(--r-md);
	}
	.knob-field .mlabel {
		align-self: flex-start;
	}
	.knob {
		position: relative;
		width: 64px;
		height: 64px;
		touch-action: none;
		cursor: ns-resize;
	}
	.disabled .knob {
		cursor: not-allowed;
	}
	.knob svg {
		width: 100%;
		height: 100%;
		display: block;
	}
	.knob.dragging svg,
	.knob:hover svg {
		filter: brightness(1.12);
	}
	.knob svg {
		transition: filter var(--fast) var(--ease);
	}
	/* Real range input, visually hidden but focusable and keyboard-operable */
	.knob input[type='range'] {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		opacity: 0;
		margin: 0;
		cursor: inherit;
	}
	.knob input[type='range']:focus-visible {
		opacity: 1;
		outline: 2px solid var(--accent);
		outline-offset: 3px;
		border-radius: 50%;
	}
	.readout {
		display: flex;
		align-items: baseline;
		justify-content: center;
		gap: 8px;
		width: 100%;
	}
	.edge {
		font-size: 0.5625rem;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: var(--ink-faint);
	}
	.value {
		font-family: var(--font-mono);
		font-size: var(--t-small);
		color: var(--ink);
		font-variant-numeric: tabular-nums;
	}
	.disabled .value {
		color: var(--ink-faint);
	}
</style>
