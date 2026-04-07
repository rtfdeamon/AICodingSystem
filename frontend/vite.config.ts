/// <reference types="vitest" />
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    css: false,
  },
  server: {
    port: parseInt(process.env.PORT || "3000", 10),
    host: "0.0.0.0",
    proxy: {
      "/api": {
        target: process.env.VITE_API_URL || "http://127.0.0.1:8010",
        changeOrigin: true,
      },
      "/ws": {
        target: (process.env.VITE_WS_URL || "ws://127.0.0.1:8010"),
        ws: true,
        changeOrigin: true,
      },
    },
  },
});
