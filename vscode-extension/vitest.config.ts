import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    alias: {
      // The vscode module is injected at runtime by VS Code — stub it for unit tests.
      vscode: new URL("./src/__mocks__/vscode.ts", import.meta.url).pathname,
    },
  },
});
