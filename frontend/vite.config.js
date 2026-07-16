import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Proxy API + WebSocket calls to the FastAPI backend on :8000
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
      "/ws": { target: "ws://localhost:8000", ws: true },
    },
  },
});
