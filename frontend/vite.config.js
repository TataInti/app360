import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,   // Puerto donde corre React
    proxy: {
      "/api": {
        target: "http://localhost:5100", // Flask corre acá
        changeOrigin: true,
      },
    },
  },
})
