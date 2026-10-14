import { defineConfig } from 'vite'
import uni from '@dcloudio/vite-plugin-uni'

// https://vitejs.dev/config/
export default defineConfig({
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
  ],
  server: {
    proxy: {
      '/api': {
        target: process.env.VITE_PROXY_TARGET || 'http://127.0.0.1:3001',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
        secure: true,
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
