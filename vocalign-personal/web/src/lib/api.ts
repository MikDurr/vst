const BASE = 'http://localhost:8010';

export type Renderer = 'praat' | 'world' | 'rubberband' | 'signalsmith';

export interface AlignParams {
	guideFile: Blob;
	guideName: string;
	dubFile: Blob;
	dubName: string;
	tightness: number;
	maxShiftS: number;
	pitchStrength: number;
	nearestOctave: boolean;
	renderer: Renderer;
}

export interface AlignResult {
	blob: Blob;
	durationS: number;
	meanShiftMs: number;
	pitchMatched: boolean;
	renderer: string;
	channels: number;
}

export async function alignTakes(p: AlignParams): Promise<AlignResult> {
	const form = new FormData();
	form.append('guide_file', p.guideFile, p.guideName);
	form.append('dub_file', p.dubFile, p.dubName);
	form.append('tightness', String(p.tightness));
	form.append('max_shift_s', String(p.maxShiftS));
	form.append('pitch_strength', String(p.pitchStrength));
	form.append('nearest_octave', String(p.nearestOctave));
	form.append('renderer', p.renderer);

	let res: Response;
	try {
		res = await fetch(`${BASE}/api/align`, { method: 'POST', body: form });
	} catch {
		throw new Error(
			`Can't reach the engine on ${BASE}. Start it with ./run.sh (or uvicorn api.main:app --port 8010).`
		);
	}
	if (!res.ok) {
		let detail = await res.text().catch(() => '');
		try {
			detail = JSON.parse(detail).detail ?? detail;
		} catch {
			/* plain text */
		}
		throw new Error(detail || `${res.status} ${res.statusText}`);
	}
	return {
		blob: await res.blob(),
		durationS: Number(res.headers.get('X-Align-Duration-S') ?? 0),
		meanShiftMs: Number(res.headers.get('X-Align-Mean-Shift-Ms') ?? 0),
		pitchMatched: res.headers.get('X-Align-Pitch-Matched') === '1',
		renderer: res.headers.get('X-Align-Renderer') ?? '',
		channels: Number(res.headers.get('X-Align-Channels') ?? 1)
	};
}

export async function engineUp(): Promise<boolean> {
	try {
		const r = await fetch(`${BASE}/api/health`, { signal: AbortSignal.timeout(2500) });
		return r.ok;
	} catch {
		return false;
	}
}
