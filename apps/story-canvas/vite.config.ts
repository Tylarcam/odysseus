import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  base: "/static/story-canvas/",
  build: {
    outDir: path.resolve(__dirname, "../../static/story-canvas"),
    emptyOutDir: true,
    sourcemap: true,
  },
  server: {
    port: 5178,
    proxy: {
      "/api": "http://127.0.0.1:7000",
    },
  },
});
