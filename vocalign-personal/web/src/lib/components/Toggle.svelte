<script lang="ts">
	interface Props { checked: boolean; label: string; disabled?: boolean; }
	let { checked = $bindable(), label, disabled = false }: Props = $props();
</script>

<button
	type="button"
	role="switch"
	aria-checked={checked}
	aria-label={label}
	{disabled}
	class="toggle"
	class:on={checked}
	onclick={() => (checked = !checked)}
>
	<span class="knob"></span>
</button>

<style>
	.toggle {
		width: 34px;
		height: 19px;
		border-radius: 999px;
		border: 1px solid var(--line);
		background: var(--surface-sunken);
		padding: 0;
		position: relative;
		transition: background var(--fast) var(--ease), border-color var(--fast) var(--ease);
		flex: none;
	}
	.toggle.on { background: var(--accent); border-color: var(--accent); }
	.toggle:disabled { opacity: 0.45; }
	.knob {
		position: absolute;
		top: 2px; left: 2px;
		width: 13px; height: 13px;
		border-radius: 50%;
		background: var(--ink-dim);
		transition: transform var(--med) var(--ease), background var(--fast) var(--ease);
	}
	.toggle.on .knob { transform: translateX(15px); background: var(--accent-ink); }
</style>
