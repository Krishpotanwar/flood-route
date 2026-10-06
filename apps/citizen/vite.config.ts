import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const proxy = {
  "/v1": {
    target: process.env.FLOODROUTE_DEV_API_URL ?? "http://127.0.0.1:8080",
    changeOrigin: true,
  },
};

export default defineConfig({
  base: "./",
  plugins: [react()],
  server: {
    port: 5173,
    proxy,
  },
  preview: { proxy },
  build: {
    target: "es2022",
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      output: {
        manualChunks: {
          react: ["react", "react-dom"],
          maplibre: ["maplibre-gl"],
        },
      },
    },
  },
});
