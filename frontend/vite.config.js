import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  // ⚠️ CHANGE THIS to your actual GitHub repo name
  base: '/job-scout/',
  build: {
    outDir: 'dist',
  },
});
