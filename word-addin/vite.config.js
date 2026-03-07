import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import fs from "fs";
import path from "path";

const certsExist =
  fs.existsSync(path.resolve("certs/localhost.key")) &&
  fs.existsSync(path.resolve("certs/localhost.crt"));

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3001,
    https: certsExist
      ? {
          key: fs.readFileSync(path.resolve("certs/localhost.key")),
          cert: fs.readFileSync(path.resolve("certs/localhost.crt")),
        }
      : undefined,
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
