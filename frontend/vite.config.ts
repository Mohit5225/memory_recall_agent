import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path' // Node.js path module for resolving

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'), // '@' now points to your src folder
    },
  },
})