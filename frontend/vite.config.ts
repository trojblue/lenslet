import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const BACKEND_URL = 'http://127.0.0.1:7070'
const PROXY_PATHS = [
  '/folders',
  '/item',
  '/thumb',
  '/file',
  '/move',
  '/delete',
  '/export-intent',
  '/export-comparison',
  '/views',
  '/search',
  '/health',
  '/events',
  '/presence',
] as const

const PROXY_CONFIG: Record<string, string> = Object.fromEntries(
  PROXY_PATHS.map((path) => [path, BACKEND_URL])
)

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'node',
  },
  server: {
    proxy: {
      // allow POST /file for uploads
      ...PROXY_CONFIG,
    },
  },
  build: {
    outDir: 'dist',
  }
})
