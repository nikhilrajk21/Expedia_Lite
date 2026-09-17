import vue from '@vitejs/plugin-vue'
import { defineConfig, loadEnv } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const environment = loadEnv(mode, '.', '')

  return {
    plugins: [vue()],
    server: {
      proxy: {
        '/api': environment.VITE_API_TARGET || 'http://127.0.0.1:8000',
      },
    },
  }
})
