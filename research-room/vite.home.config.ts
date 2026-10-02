import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/postcss';

// Same React scene as the teammate's preview, served by FastAPI in production.
export default defineConfig({
  root: fileURLToPath(new URL('./home', import.meta.url)),
  base: '/office/',
  publicDir: false,
  resolve: { alias: { '@': fileURLToPath(new URL('.', import.meta.url)) } },
  css: { postcss: { plugins: [tailwindcss()] } },
  plugins: [react()],
  build: {
    outDir: fileURLToPath(new URL('./home-dist', import.meta.url)),
    // The workspace owner requires preserving all existing files.
    emptyOutDir: false,
    sourcemap: false,
  },
});
