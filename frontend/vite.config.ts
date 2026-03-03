import { defineConfig } from "vite";
import { resolve } from "node:path";

export default defineConfig({
  build: {
    outDir: resolve(__dirname, "../deploy/vercel/public"),
    emptyOutDir: true,
  },
  test: {
    environment: "node",
  },
});
