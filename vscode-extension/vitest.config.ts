import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    // Only the TypeScript sources — never the compiled CommonJS in
    // out/ (after `npm run compile`, out/extension.test.js would be
    // discovered and fail because it imports Vitest at runtime).
    include: ["src/**/*.test.ts"],
    exclude: ["out/**", "node_modules/**"],
    alias: {
      // The vscode module is injected at runtime by VS Code — stub it for unit tests.
      vscode: new URL("./src/__mocks__/vscode.ts", import.meta.url).pathname,
    },
  },
});
