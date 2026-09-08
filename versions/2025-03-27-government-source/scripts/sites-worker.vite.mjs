import {defineConfig} from 'vite';
import {sites} from '@openai/sites-vite-plugin';

export default defineConfig({
  plugins: [sites()],
  publicDir: false,
  build: {
    ssr: 'sites/worker.mjs',
    outDir: 'dist/server',
    emptyOutDir: true,
    target: 'es2022',
    minify: true,
    rolldownOptions: {output: {entryFileNames: 'index.js'}},
  },
});
