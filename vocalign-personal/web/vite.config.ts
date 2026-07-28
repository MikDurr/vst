import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

// Port 5180, not 5173 — the vocal training studio's UI uses 5173 and these
// are separate apps that may run at the same time.
export default defineConfig({
	plugins: [sveltekit()],
	server: { port: 5180, strictPort: true }
});
