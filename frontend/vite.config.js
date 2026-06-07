import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Dev proxy: forward /api and /ws to the backend so the Vite dev server
// can sit in front without CORS issues or secret leakage.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
        changeOrigin: true,
      },
      // Cached slideshow photos are served by the backend at /photos/<file>.
      '/photos': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    rollupOptions: {
      output: {
        // Split vendor chunks for better caching
        manualChunks: {
          react: ['react', 'react-dom'],
        },
      },
    },
  },
});
