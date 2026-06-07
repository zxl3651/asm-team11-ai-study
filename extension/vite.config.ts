import { resolve } from "path";

import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";

// 번들에 남는 raw 제어문자(예: \x01)를 \xHH 이스케이프로 치환한다.
// 문자열 값은 동일하게 유지되며, 파일은 순수 출력 가능 ASCII가 되어
// 크롬 콘텐츠 스크립트의 UTF-8 검사를 안전하게 통과한다.
function escapeControlChars(): Plugin {
  return {
    name: "escape-control-chars",
    generateBundle(_options, bundle) {
      for (const chunk of Object.values(bundle)) {
        if (chunk.type === "chunk") {
          chunk.code = chunk.code.replace(
            /[\x00-\x08\x0b\x0c\x0e-\x1f]/g,
            (c) => "\\x" + c.charCodeAt(0).toString(16).padStart(2, "0")
          );
        }
      }
    },
  };
}

// content script 는 일반 스크립트(모듈 X)로 주입되므로,
// 코드 분할 없이 단일 IIFE 파일로 번들링한다.
export default defineConfig({
  plugins: [react(), escapeControlChars()],
  publicDir: "public",
  // 번들에 raw null 바이트(\x00)나 비ASCII가 섞이면 크롬이 콘텐츠 스크립트를
  // "UTF-8 아님"으로 거부한다. ascii charset 으로 모두 이스케이프해 회피.
  esbuild: {
    charset: "ascii",
  },
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
