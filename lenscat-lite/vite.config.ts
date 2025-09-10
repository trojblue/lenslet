import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/folders': 'http://127.0.0.1:7070',
      '/item': 'http://127.0.0.1:7070',
      '/thumb': 'http://127.0.0.1:7070',
      '/file': 'http://127.0.0.1:7070',
      '/search': 'http://127.0.0.1:7070',
      '/health': 'http://127.0.0.1:7070'
    }
  },
  build: {
    outDir: 'dist'
  }
})
