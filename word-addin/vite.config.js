import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import fs from "fs";
import path from "path";
import devCerts from "office-addin-dev-certs";

const certsExist =
  fs.existsSync(path.resolve("certs/localhost.key")) &&
  fs.existsSync(path.resolve("certs/localhost.crt"));

// Helper to get HTTPS options
async function getHttpsOptions() {
  if (certsExist) {
    return {
      key: fs.readFileSync(path.resolve("certs/localhost.key")),
      cert: fs.readFileSync(path.resolve("certs/localhost.crt")),
    };
  }

  try {
    const options = await devCerts.getHttpsServerOptions();
    return options;
  } catch (error) {
    console.error("Warning: Could not get office-addin-dev-certs. Add-in might fail to load.", error);
    return true; // Fallback to basic HTTPS
  }
}

export default defineConfig(async () => {
  const httpsOptions = await getHttpsOptions();

  return {
    plugins: [react()],
    server: {
      port: 3001,
      https: httpsOptions,
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
  };
});
