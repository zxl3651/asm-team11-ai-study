import { resolve } from "path";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// content script 는 일반 스크립트(모듈 X)로 주입되므로,
// 코드 분할 없이 단일 IIFE 파일로 번들링한다.
export default defineConfig({
  plugins: [react()],
  publicDir: "public",
  build: {
    outDir: "dist",
    rollupOptions: {
      input: resolve(__dirname, "src/content/index.tsx"),
      output: {
        format: "iife",
        entryFileNames: "src/content/index.js",
        inlineDynamicImports: true,
      },
    },
  },
});
