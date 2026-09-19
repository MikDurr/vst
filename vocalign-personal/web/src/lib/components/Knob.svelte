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
		/** Value restored on double-click. Omit to disable the double-click reset. */
		resetValue?: number;
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
		disabled = false,
		resetValue
	}: Props = $props();

	function clamp(v: number) {
		return Math.min(max, Math.max(min, v));
	}

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
	let inputEl: HTMLInputElement | undefined = $state();

	function onPointerDown(e: PointerEvent) {
		if (disabled) return;
		// The native range input sits underneath for a11y/keyboard only
		// (pointer-events: none in CSS) — focus it manually so keyboard
		// users can still tab to/operate it after a click or drag.
		inputEl?.focus();
		dragging = true;
		(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
	}
	function onPointerMove(e: PointerEvent) {
		if (!dragging || disabled) return;
		// Vertical drag = the plugin convention; far more precise than
		// following the pointer angle around a small circle. Hold Shift for
		// a fine pass — a flat 1:1 pixel mapping makes it nearly impossible
		// to land on an exact value across a 270° sweep.
		const sensitivity = e.shiftKey ? 8 : 1;
		const delta = -e.movementY / (180 * sensitivity);
		value = clamp(value + delta * (max - min));
	}
	function onPointerUp(e: PointerEvent) {
		dragging = false;
		(e.currentTarget as HTMLElement).releasePointerCapture?.(e.pointerId);
	}

	// Scroll = nudge by one step, same increment as an arrow key but without
	// needing focus first. Trackpads fire a stream of small deltas rather
	// than one clean notch, so accumulate and only fire once a full step's
	// worth has passed — otherwise a light trackpad graze sends the value
	// flying.
	let wheelAccum = 0;
	const WHEEL_THRESHOLD = 40;
	function onWheel(e: WheelEvent) {
		if (disabled) return;
		e.preventDefault();
		wheelAccum += e.deltaY;
		while (wheelAccum >= WHEEL_THRESHOLD) {
			value = clamp(value - step);
			wheelAccum -= WHEEL_THRESHOLD;
		}
		while (wheelAccum <= -WHEEL_THRESHOLD) {
			value = clamp(value + step);
			wheelAccum += WHEEL_THRESHOLD;
		}
	}

	function onDblClick() {
		if (disabled || resetValue === undefined) return;
		value = clamp(resetValue);
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
		onwheel={onWheel}
		ondblclick={onDblClick}
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
			bind:this={inputEl}
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
	/* Real range input, visually hidden but focusable and keyboard-operable.
	   pointer-events: none keeps it out of the hit-test entirely — otherwise
	   a click/drag lands on the input first and the browser's native
	   jump-to-click-position behavior fires before onPointerDown runs,
	   snapping the value to an unrelated spot right before the vertical-drag
	   handler takes over. All pointer interaction goes through the wrapper
	   div above; this input only handles keyboard (arrow keys, Home/End)
	   once focused via inputEl.focus() in onPointerDown. */
	.knob input[type='range'] {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		opacity: 0;
		margin: 0;
		pointer-events: none;
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
