import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3001,
    // For sideloading in Word Online / Desktop, HTTPS is needed.
    // Install: npm i -D @vitejs/plugin-basic-ssl
    // Then add basicSsl() to plugins array above.
    // For local browser testing, HTTP works fine.
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
    },
  },
  build: {
    outDir: "dist",
  },
});
