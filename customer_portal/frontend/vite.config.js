import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';

// Build output lands in ../static/spa, already inside Django's
// STATICFILES_DIRS, so no extra Django settings are needed to serve it.
// Fixed (non-hashed) filenames keep the wiring in templates/spa/shell.html
// simple - cache-busting is handled there via a manual ?v= query param
// (settings.SPA_BUILD_VERSION) instead of a Vite manifest.
export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api/v1': 'http://127.0.0.1:8000',
    },
  },
  build: {
    outDir: '../static/spa',
    emptyOutDir: true,
    rollupOptions: {
      output: {
        entryFileNames: 'app.js',
        chunkFileNames: 'app-[name].js',
        assetFileNames: (assetInfo) => {
          if (assetInfo.name && assetInfo.name.endsWith('.css')) {
            return 'app.css';
          }
          return 'app-[name][extname]';
        },
      },
    },
  },
});
