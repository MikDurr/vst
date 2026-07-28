/** Synchronised multi-stem transport.
 *
 *  Separation is only half the job — the question you actually have is "did it
 *  leave anything of the snare in the vocal?", and you answer it by soloing
 *  stems against each other in place, not by exporting four files and dragging
 *  them into a DAW.
 *
 *  Four <audio> elements can't do this: each has its own clock, they drift
 *  audibly within seconds, and .play() on four of them doesn't start four
 *  things at once. So every stem gets an AudioBufferSourceNode scheduled
 *  against one shared AudioContext clock, all with the same start time. That's
 *  sample-accurate by construction and stays that way.
 *
 *  The cost is that seeking means tearing down and rescheduling every source,
 *  since a started BufferSource can't be repositioned. That's cheap — the
 *  decoded buffers are reused, only the nodes are rebuilt.
 */

export interface StemAudio {
	name: string;
	blob: Blob;
}

/** Ramp length for gain changes. Stepping a gain discontinuously produces an
 *  audible click, which on a solo button you'd hear as part of the stem. */
const RAMP_S = 0.015;

export class StemPlayer {
	private ctx: AudioContext | null = null;
	private buffers = new Map<string, AudioBuffer>();
	private gains = new Map<string, GainNode>();
	private sources = new Map<string, AudioBufferSourceNode>();
	private levels = new Map<string, number>();

	/** Context time at which the current playback run started. */
	private startedAt = 0;
	/** Offset into the material that that run started from. */
	private offset = 0;

	duration = 0;
	playing = false;
	names: string[] = [];

	private ensureCtx(): AudioContext {
		if (!this.ctx) {
			const AC: typeof AudioContext =
				window.AudioContext ??
				(window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
			this.ctx = new AC();
		}
		return this.ctx;
	}

	/** Decode a set of stems, replacing whatever was loaded before.
	 *  Returns the decoded buffers so the caller can draw waveforms from the
	 *  same decode rather than paying for a second one. */
	async load(stems: StemAudio[]): Promise<Map<string, AudioBuffer>> {
		this.stop();
		const ctx = this.ensureCtx();
		this.buffers.clear();
		this.gains.clear();
		this.levels.clear();

		// Decode in parallel — four stems of a 4-minute song is a few seconds
		// of work serially, and none of them depend on each other.
		const decoded = await Promise.all(
			stems.map(async (s) => [s.name, await ctx.decodeAudioData(await s.blob.arrayBuffer())] as const)
		);

		for (const [name, buf] of decoded) {
			this.buffers.set(name, buf);
			const g = ctx.createGain();
			g.gain.value = 1;
			g.connect(ctx.destination);
			this.gains.set(name, g);
			this.levels.set(name, 1);
		}
		this.names = decoded.map(([n]) => n);
		this.duration = Math.max(0, ...decoded.map(([, b]) => b.duration));
		this.offset = 0;
		return new Map(this.buffers);
	}

	/** Where the playhead is now, in seconds. */
	position(): number {
		if (!this.playing || !this.ctx) return this.offset;
		const t = this.offset + (this.ctx.currentTime - this.startedAt);
		return Math.min(t, this.duration);
	}

	private schedule(from: number): void {
		const ctx = this.ensureCtx();
		this.teardownSources();
		// A small lead so every source is scheduled before the clock reaches
		// the start time; starting "now" can let the first node begin a block
		// ahead of the last one.
		const when = ctx.currentTime + 0.03;
		for (const [name, buf] of this.buffers) {
			const src = ctx.createBufferSource();
			src.buffer = buf;
			src.connect(this.gains.get(name)!);
			src.start(when, Math.min(from, buf.duration));
			this.sources.set(name, src);
		}
		this.startedAt = when;
		this.offset = from;
	}

	private teardownSources(): void {
		for (const src of this.sources.values()) {
			try {
				src.onended = null;
				src.stop();
			} catch {
				/* already stopped */
			}
			src.disconnect();
		}
		this.sources.clear();
	}

	async play(from?: number): Promise<void> {
		if (!this.buffers.size) return;
		const ctx = this.ensureCtx();
		// Browsers start the context suspended until a user gesture.
		if (ctx.state === 'suspended') await ctx.resume();
		let at = from ?? this.position();
		if (at >= this.duration - 0.01) at = 0; // restart rather than no-op at the end
		this.schedule(at);
		this.playing = true;
	}

	pause(): void {
		if (!this.playing) return;
		this.offset = this.position();
		this.teardownSources();
		this.playing = false;
	}

	stop(): void {
		this.teardownSources();
		this.playing = false;
		this.offset = 0;
	}

	seek(t: number): void {
		const at = Math.max(0, Math.min(t, this.duration));
		if (this.playing) this.schedule(at);
		else this.offset = at;
	}

	/** Has playback run off the end? Polled by the UI's rAF loop, which is
	 *  already running — cheaper and less fiddly than an `onended` per source,
	 *  which would also fire on every seek and teardown. */
	finished(): boolean {
		return this.playing && this.duration > 0 && this.position() >= this.duration - 0.01;
	}

	setGain(name: string, value: number): void {
		this.levels.set(name, value);
		this.applyGain(name, value);
	}

	private applyGain(name: string, value: number): void {
		const g = this.gains.get(name);
		if (!g || !this.ctx) return;
		const now = this.ctx.currentTime;
		g.gain.cancelScheduledValues(now);
		g.gain.setValueAtTime(g.gain.value, now);
		g.gain.linearRampToValueAtTime(value, now + RAMP_S);
	}

	/** Apply the solo/mute state across every stem at once.
	 *  Solo wins over mute, matching every DAW: if anything is soloed, only
	 *  soloed stems are heard, regardless of their mute buttons. */
	applyMix(soloed: Set<string>, muted: Set<string>): void {
		const anySolo = soloed.size > 0;
		for (const name of this.buffers.keys()) {
			const audible = anySolo ? soloed.has(name) : !muted.has(name);
			this.applyGain(name, audible ? (this.levels.get(name) ?? 1) : 0);
		}
	}

	dispose(): void {
		this.stop();
		for (const g of this.gains.values()) g.disconnect();
		this.gains.clear();
		this.buffers.clear();
		void this.ctx?.close();
		this.ctx = null;
	}
}

/** Peaks straight from an already-decoded buffer — the player has decoded
 *  every stem anyway, so drawing shouldn't decode them a second time. */
export function peaksFromBuffer(buf: AudioBuffer, buckets = 1400): Float32Array {
	const chans = Array.from({ length: buf.numberOfChannels }, (_, c) => buf.getChannelData(c));
	const out = new Float32Array(buckets);
	const per = Math.max(1, Math.floor(buf.length / buckets));
	for (let b = 0; b < buckets; b++) {
		let peak = 0;
		const start = b * per;
		const end = Math.min(buf.length, start + per);
		for (let i = start; i < end; i++) {
			let s = 0;
			for (const ch of chans) s += ch[i];
			s = Math.abs(s / chans.length);
			if (s > peak) peak = s;
		}
		out[b] = peak;
	}
	// Normalise per lane so a quiet stem — a bass part, say — still reads as a
	// waveform instead of a flat line. These are pictures, not meters.
	let max = 0;
	for (const v of out) if (v > max) max = v;
	if (max > 0) for (let i = 0; i < out.length; i++) out[i] /= max;
	return out;
}
