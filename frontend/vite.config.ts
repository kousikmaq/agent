import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Frontend dev server proxies API calls to the FastAPI backend on :8000,
// so the browser can use relative "/api/v1/..." URLs with no CORS friction.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
