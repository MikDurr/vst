import { zip, type Zippable } from 'fflate';

export interface ZipEntry {
	/** Path inside the archive, e.g. "Verse Guide/Take 2_aligned.wav" */
	path: string;
	blob: Blob;
}

/** Bundle files into a .zip and hand it to the browser as one download,
 *  instead of firing N separate (and browser-throttled) downloads. */
export async function zipAndDownload(entries: ZipEntry[], zipName: string): Promise<void> {
	if (!entries.length) return;

	const files: Zippable = {};
	for (const e of entries) {
		files[e.path] = new Uint8Array(await e.blob.arrayBuffer());
	}

	const zipped = await new Promise<Uint8Array>((resolve, reject) => {
		zip(files, { level: 6 }, (err, data) => (err ? reject(err) : resolve(data)));
	});

	const url = URL.createObjectURL(new Blob([zipped as BlobPart], { type: 'application/zip' }));
	const a = document.createElement('a');
	a.href = url;
	a.download = zipName;
	a.click();
	// click() synchronously hands the browser the download; keeping the
	// object URL alive past that just leaks memory.
	setTimeout(() => URL.revokeObjectURL(url), 1000);
}
