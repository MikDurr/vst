import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

// Port 5190: the vocal training studio's UI uses 5173 and vocalign's uses
// 5180, and all three may run at the same time.
export default defineConfig({
	plugins: [sveltekit()],
	server: { port: 5190, strictPort: true }
});
