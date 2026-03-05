import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const backendUrl = env.VITE_BACKEND_URL || "http://localhost:8000";
  const port = parseInt(env.VITE_PORT || "5173");

  return {
    plugins: [react()],
    server: {
      port,
      proxy: {
        "/format": { target: backendUrl, timeout: 0 },
        "/download": { target: backendUrl, timeout: 0 },
        "/health": { target: backendUrl, timeout: 0 },
      },
    },
  };
});
