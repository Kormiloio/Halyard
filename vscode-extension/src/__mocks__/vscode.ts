// Minimal vscode stub for unit tests — only the surface used by tested exports.
export const workspace = {
  getConfiguration: () => ({
    get: (_key: string, fallback: unknown) => fallback,
  }),
  workspaceFolders: undefined,
};
