import { resolve } from "path";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// 사이드패널 HTML 과 백그라운드 서비스워커를 각각 번들링한다.
export default defineConfig({
  plugins: [react()],
  publicDir: "public",
  build: {
    outDir: "dist",
    rollupOptions: {
      input: {
        sidepanel: resolve(__dirname, "src/sidepanel/index.html"),
        background: resolve(__dirname, "src/background/index.ts"),
      },
      output: {
        entryFileNames: "src/[name]/index.js",
      },
    },
  },
});
