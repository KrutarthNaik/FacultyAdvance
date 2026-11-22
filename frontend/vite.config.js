import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

if (process.env.VERCEL === '1' && !process.env.VITE_API_URL) {
  throw new Error('Set VITE_API_URL to the deployed Django API base URL before deploying the frontend.')
}

if (process.env.VERCEL === '1') {
  const uploadLimit = Number(process.env.VITE_EVIDENCE_UPLOAD_MAX_MB)
  if (!Number.isInteger(uploadLimit) || uploadLimit < 1 || uploadLimit > 4) {
    throw new Error('Set VITE_EVIDENCE_UPLOAD_MAX_MB to an integer from 1 to 4 for Vercel deployments.')
  }
}

export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
  test: { environment: 'jsdom', setupFiles: './src/test-setup.js' },
})
