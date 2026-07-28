/** Decode an audio file in the browser and reduce it to per-column peaks for
 *  drawing. Done client-side so loading a take paints a waveform instantly,
 *  without a server round-trip just to get a picture. */
export async function peaksFromBlob(blob: Blob, buckets = 1400): Promise<Float32Array> {
	const AC: typeof AudioContext =
		window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
	const ctx = new AC();
	try {
		const buf = await ctx.decodeAudioData(await blob.arrayBuffer());
		// Mono-sum for display only; rendering elsewhere keeps real channels.
		const n = buf.length;
		const chans = Array.from({ length: buf.numberOfChannels }, (_, c) => buf.getChannelData(c));
		const out = new Float32Array(buckets);
		const per = Math.max(1, Math.floor(n / buckets));
		for (let b = 0; b < buckets; b++) {
			let peak = 0;
			const start = b * per;
			const end = Math.min(n, start + per);
			for (let i = start; i < end; i++) {
				let s = 0;
				for (const ch of chans) s += ch[i];
				s = Math.abs(s / chans.length);
				if (s > peak) peak = s;
			}
			out[b] = peak;
		}
		// Normalise so a quiet take still fills its lane — this is a picture,
		// not a meter.
		let max = 0;
		for (const v of out) if (v > max) max = v;
		if (max > 0) for (let i = 0; i < out.length; i++) out[i] /= max;
		return out;
	} finally {
		void ctx.close();
	}
}

export function durationLabel(s: number): string {
	if (!isFinite(s) || s < 0) return '0:00';
	const m = Math.floor(s / 60);
	const sec = Math.floor(s % 60);
	return `${m}:${String(sec).padStart(2, '0')}`;
}
