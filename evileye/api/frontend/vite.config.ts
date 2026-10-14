import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: '../static',
    emptyOutDir: true,
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('/node_modules/@xyflow/') || id.includes('/node_modules/d3-')) return 'pipeline-graph';
          if (id.includes('/node_modules/@rjsf/') || id.includes('/node_modules/ajv') || id.includes('/node_modules/fast-deep-equal')) return 'schema-forms';
        },
      },
    },
  },
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8181',
      '/ready': 'http://127.0.0.1:8181',
    },
  },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.{ts,tsx}'],
    setupFiles: ['./src/test/setup.ts'],
  },
});
