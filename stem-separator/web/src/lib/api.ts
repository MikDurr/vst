const BASE = 'http://localhost:8020';

export type Engine = 'demucs' | 'quick';
export type Mode = 'four' | 'two';
export type JobStatus = 'queued' | 'running' | 'done' | 'error' | 'cancelled';

export interface ModelInfo {
	id: string;
	label: string;
	note: string;
}

export interface Health {
	status: string;
	demucs: boolean;
	device: string;
	models: ModelInfo[];
	default_model: string;
}

export interface Job {
	id: string;
	source_name: string;
	engine: Engine;
	status: JobStatus;
	progress: number;
	message: string;
	error: string | null;
	stems: string[];
	device: string;
	elapsed_s: number;
}

export interface SeparateParams {
	file: Blob;
	name: string;
	engine: Engine;
	model: string;
	mode: Mode;
	shifts: number;
	device?: string | null;
}

const OFFLINE = `Can't reach the engine on ${BASE}. Start it with ./run.sh (or uvicorn api.main:app --port 8020).`;
const UNRESPONSIVE = `The engine on ${BASE} accepted the connection but didn't answer. It may be suspended — check for a stopped process (\`ps -o stat\` showing T) and restart ./run.sh.`;

/** Status polls carry a timeout; a separation can take minutes, but the poll
 *  that reports on it is a trivial read and should never take seconds. Without
 *  one, an engine that is up but not responding — a suspended process holds its
 *  port open and simply never replies — leaves fetch pending forever and the UI
 *  showing a progress bar that will never move again. */
async function request(path: string, init?: RequestInit, timeoutMs?: number): Promise<Response> {
	let res: Response;
	try {
		res = await fetch(`${BASE}${path}`, {
			...init,
			...(timeoutMs ? { signal: AbortSignal.timeout(timeoutMs) } : {})
		});
	} catch (e) {
		// A timeout means something is listening but wedged; a network error
		// means nothing is there at all. Different fixes, so different messages.
		throw new Error(e instanceof DOMException && e.name === 'TimeoutError' ? UNRESPONSIVE : OFFLINE);
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
	return res;
}

export async function health(): Promise<Health | null> {
	try {
		const r = await fetch(`${BASE}/api/health`, { signal: AbortSignal.timeout(2500) });
		return r.ok ? await r.json() : null;
	} catch {
		return null;
	}
}

export async function startSeparation(p: SeparateParams): Promise<Job> {
	const form = new FormData();
	form.append('file', p.file, p.name);
	form.append('engine', p.engine);
	form.append('model', p.model);
	form.append('mode', p.mode);
	form.append('shifts', String(p.shifts));
	if (p.device) form.append('device', p.device);
	const res = await request('/api/separate', { method: 'POST', body: form });
	return res.json();
}

export async function jobStatus(id: string): Promise<Job> {
	return (await request(`/api/jobs/${id}`, undefined, 10_000)).json();
}

export async function cancelJob(id: string): Promise<void> {
	// Best-effort: the job may already have finished or been swept, and there's
	// nothing useful the UI could do about either.
	await fetch(`${BASE}/api/jobs/${id}`, { method: 'DELETE' }).catch(() => undefined);
}

export async function fetchStem(id: string, name: string): Promise<Blob> {
	return (await request(`/api/jobs/${id}/stems/${encodeURIComponent(name)}`)).blob();
}

export function stemUrl(id: string, name: string): string {
	return `${BASE}/api/jobs/${id}/stems/${encodeURIComponent(name)}`;
}

export function zipUrl(id: string): string {
	return `${BASE}/api/jobs/${id}/zip`;
}
