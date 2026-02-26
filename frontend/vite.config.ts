// vite.config.ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          // Core React
          "vendor-react": ["react", "react-dom"],

          // Router
          "vendor-router": ["react-router-dom"],

          // State management
          "vendor-state": ["zustand"],

          // UI Components
          "vendor-ui": [
            "react-hot-toast",
            "lucide-react",
            "react-textarea-autosize",
          ],

          // Markdown processing (usually large)
          "vendor-markdown": [
            "react-markdown",
            "remark-gfm",
            "highlight.js",
          ],
        },
      },
    },
    target: "esnext",
    minify: "esbuild",
  },
});
