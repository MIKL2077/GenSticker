import { defineConfig } from 'vite'
import uni from '@dcloudio/vite-plugin-uni'
import { HttpsProxyAgent } from 'https-proxy-agent'
import weixinPackage from './scripts/weixin-package.cjs'

// https://vitejs.dev/config/
export default defineConfig({
  build: process.env.UNI_PLATFORM === 'mp-weixin' ? {
    minify: process.env.NODE_ENV === 'production' ? 'terser' : false,
    // WeChat transpiles this output again. Mangling can reuse a hoisted optional
    // chaining temporary's name for a nested const, which its Babel pass then
    // treats as a read-only assignment and aborts page initialization.
    terserOptions: { mangle: false },
  } : undefined,
  plugins: [
    {
      name: 'gensticker-custom-navigation',
      enforce: 'pre',
      transform(code, id) {
        // All pages use custom navigation. uni-app's native shadow preloader
        // constructs a malformed relative HTTPS path in this pinned runtime.
        // Remove only that optional preloader, keeping wx.preloadAssets intact.
        if (!id.includes('/uni-mp-weixin/dist/uni.mp.esm.js')) return
        return code.replace(/if \(!\(process\.env\.NODE_ENV !== 'production'\)[\s\S]*?const protocol = 'https';[\s\S]*?src: protocol \+ __UNI_PRELOAD_SHADOW_IMAGE__[\s\S]*?\}, 3000\);\s*\}/, '')
      },
    },
    uni(),
    {
      name: 'gensticker-weixin-package',
      apply: 'build',
      closeBundle: {
        order: 'post',
        sequential: true,
        handler() {
          if (process.env.UNI_PLATFORM !== 'mp-weixin' || process.env.NODE_ENV !== 'production') return
          const report = weixinPackage.optimizePackage(process.env.UNI_OUTPUT_DIR)
          console.log(`WeChat package: ${report.packageBytes} bytes; images/audio: ${report.mediaBytes} / ${report.mediaLimitBytes} bytes; lossless PNG savings: ${report.savedBytes} bytes`)
        },
      },
    },
  ],
  server: {
    proxy: {
      '/api': {
        target: process.env.VITE_PROXY_TARGET || 'http://127.0.0.1:3001',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
        secure: true,
        // Optional development transport. Keep TLS validation and the real API;
        // this does not affect the WeChat build or change system proxy settings.
        agent: process.env.VITE_PROXY_URL ? new HttpsProxyAgent(process.env.VITE_PROXY_URL) : undefined,
        proxyTimeout: 65000,
        configure: (proxy, options) => {
          proxy.on('error', (err, req, res) => {
            console.log('proxy error', err);
          });
          proxy.on('proxyReq', (proxyReq, req, res) => {
            console.log('Sending Request to the Target:', req.method, req.url);
          });
          proxy.on('proxyRes', (proxyRes, req, res) => {
            console.log('Received Response from the Target:', proxyRes.statusCode, req.url);
          });
        },
      }
    }
  }
})
