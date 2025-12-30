import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'node',
  },
  server: {
    proxy: {
      '/folders': 'http://127.0.0.1:7070',
      '/item': 'http://127.0.0.1:7070',
      '/thumb': 'http://127.0.0.1:7070',
      '/file': 'http://127.0.0.1:7070',
      '/move': 'http://127.0.0.1:7070',
      '/delete': 'http://127.0.0.1:7070',
      '/export-intent': 'http://127.0.0.1:7070',
      '/views': 'http://127.0.0.1:7070',
      // allow POST /file for uploads
      '/search': 'http://127.0.0.1:7070',
      '/health': 'http://127.0.0.1:7070'
    }
  },
  build: {
    outDir: 'dist',
  }
})
