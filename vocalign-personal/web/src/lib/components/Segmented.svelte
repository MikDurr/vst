<script lang="ts">
	/* Segmented control instead of a <select>: only 2-3 options each, and
	   showing them beats hiding them behind a menu in a control panel. */
	interface Props {
		label: string;
		value: string;
		options: { value: string; label: string }[];
		disabled?: boolean;
	}
	let { label, value = $bindable(), options, disabled = false }: Props = $props();
</script>

<div class="field">
	<span class="mlabel">{label}</span>
	<div class="seg" role="radiogroup" aria-label={label}>
		{#each options as o (o.value)}
			<button
				type="button"
				role="radio"
				aria-checked={value === o.value}
				class:sel={value === o.value}
				{disabled}
				onclick={() => (value = o.value)}
			>{o.label}</button>
		{/each}
	</div>
</div>

<style>
	.field { display: flex; flex-direction: column; gap: 7px; }
	.seg {
		display: flex;
		background: var(--surface-sunken);
		border: 1px solid var(--line-soft);
		border-radius: var(--r-sm);
		padding: 2px;
		gap: 2px;
	}
	.seg button {
		flex: 1;
		border: 0;
		background: transparent;
		color: var(--ink-muted);
		font-size: var(--t-micro);
		font-weight: 600;
		letter-spacing: 0.05em;
		text-transform: uppercase;
		padding: 6px 4px;
		border-radius: 3px;
		transition: background var(--fast) var(--ease), color var(--fast) var(--ease);
	}
	.seg button:hover:not(:disabled):not(.sel) { color: var(--ink-dim); background: var(--surface); }
	.seg button.sel { background: var(--surface-raised); color: var(--ink); }
	.seg button:disabled { opacity: 0.45; }
</style>
