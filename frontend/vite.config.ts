import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: { outDir: 'dist' },
  server: {
    port: 5173,
    proxy: {
      '/ws':           { target: 'ws://localhost:8000',   ws: true, changeOrigin: true },
      '/goal':         { target: 'http://localhost:8000', changeOrigin: true },
      '/agents':       { target: 'http://localhost:8000', changeOrigin: true },
      '/agora':        { target: 'http://localhost:8000', changeOrigin: true },
      '/tasks':        { target: 'http://localhost:8000', changeOrigin: true },
      '/arbitration':  { target: 'http://localhost:8000', changeOrigin: true },
      '/x':            { target: 'http://localhost:8000', changeOrigin: true },
      '/reset':        { target: 'http://localhost:8000', changeOrigin: true },
      '/debug':        { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
})
