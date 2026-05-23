type WorkspaceConfiguration = {
  get(key: string, fallback: unknown): unknown;
};

type WorkspaceState = {
  get<T>(key: string): T | undefined;
  update(key: string, value: unknown): Promise<void>;
};

type Disposable = {
  dispose(): void;
};

const workspaceConfiguration: Record<string, Record<string, unknown>> = {
  halyard: {},
};

const workspaceStateData: Record<string, unknown> = {};

const registeredCommands: Record<string, (...args: unknown[]) => unknown> = {};

export const workspace = {
  workspaceFolders: undefined as { uri: { fsPath: string } }[] | undefined,
  getConfiguration(section: string): WorkspaceConfiguration {
    return {
      get: (key: string, fallback: unknown) => {
        return workspaceConfiguration[section]?.[key] ?? fallback;
      },
    };
  },
  workspaceState: {
    get<T>(key: string): T | undefined {
      return workspaceStateData[key] as T | undefined;
    },
    update(key: string, value: unknown): Promise<void> {
      if (value === undefined) {
        delete workspaceStateData[key];
      } else {
        workspaceStateData[key] = value;
      }
      return Promise.resolve();
    },
  },
  onDidChangeTextDocument: (_listener: unknown): Disposable => ({
    dispose: () => {},
  }),
};

export const commands = {
  registerCommand: (
    command: string,
    callback: (...args: unknown[]) => unknown,
  ): Disposable => {
    registeredCommands[command] = callback;
    return { dispose: () => {} };
  },
  executeCommand: async (command: string, ...args: unknown[]): Promise<unknown> => {
    return registeredCommands[command]?.(...args);
  },
};

export const window = {
  createStatusBarItem: (): { show(): void; dispose(): void; text?: string; tooltip?: string } => ({
    show: () => {},
    dispose: () => {},
  }),
  showInformationMessage: async (): Promise<undefined> => undefined,
  showWarningMessage: async (): Promise<undefined> => undefined,
  showInputBox: async (): Promise<string | undefined> => undefined,
  onDidChangeActiveTextEditor: (_listener: unknown): Disposable => ({
    dispose: () => {},
  }),
  onDidChangeWindowState: (_listener: unknown): Disposable => ({
    dispose: () => {},
  }),
};

export const StatusBarAlignment = {
  Left: 1,
  Right: 2,
};

export function setConfiguration(section: string, key: string, value: unknown): void {
  workspaceConfiguration[section] = workspaceConfiguration[section] ?? {};
  workspaceConfiguration[section][key] = value;
}

export function resetVscodeMocks(): void {
  Object.keys(workspaceStateData).forEach((key) => {
    delete workspaceStateData[key];
  });
  Object.keys(workspaceConfiguration).forEach((section) => {
    workspaceConfiguration[section] = {};
  });
  Object.keys(registeredCommands).forEach((key) => {
    delete registeredCommands[key];
  });
  workspace.workspaceFolders = undefined;
}
