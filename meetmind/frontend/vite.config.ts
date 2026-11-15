import { defineConfig, loadEnv } from 'vite';
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '');
  return { css: { postcss: { plugins: [] } }, server: { proxy: { '/api': env.MEETMIND_BACKEND_URL || 'http://127.0.0.1:8000' } } };
});
