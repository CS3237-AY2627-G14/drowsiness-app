import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import type { ServerOptions as HttpsOptions } from 'node:https'
import { defineConfig, loadEnv } from 'vite'
import viteReact, { reactCompilerPreset } from '@vitejs/plugin-react'
import babel from '@rolldown/plugin-babel'
import tailwindcss from '@tailwindcss/vite'

const loadDevelopmentTls = (
  env: Record<string, string>,
): HttpsOptions | undefined => {
  if (Boolean(env.DEV_TLS_CERT) !== Boolean(env.DEV_TLS_KEY)) {
    throw new Error('Set both DEV_TLS_CERT and DEV_TLS_KEY to enable HTTPS.')
  }
  if (!env.DEV_TLS_CERT || !env.DEV_TLS_KEY) return undefined
  const certificatePath = resolve(env.DEV_TLS_CERT)
  const keyPath = resolve(env.DEV_TLS_KEY)
  const cert = readFileSync(certificatePath)
  const key = readFileSync(keyPath)
  return { cert, key }
}

export default defineConfig(({ mode }) => {
  const workingDirectory = process.cwd()
  const env = loadEnv(mode, workingDirectory, '')
  const https = loadDevelopmentTls(env)
  const proxy = {
    '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true, ws: true },
  }
  return {
    resolve: { tsconfigPaths: true },
    plugins: [
      tailwindcss(),
      viteReact(),
      babel({ presets: [reactCompilerPreset()] }),
    ],
    server: { host: '0.0.0.0', port: 3000, strictPort: true, https, proxy },
    preview: { host: '0.0.0.0', port: 3000, strictPort: true, https, proxy },
  }
})
