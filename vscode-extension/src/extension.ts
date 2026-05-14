import * as vscode from "vscode";
import { execFile, spawn } from "node:child_process";

type SessionState = {
  startedAt: number;
  activeSeconds: number;
  idleSeconds: number;
  lastActivityAt: number;
  initialBranch?: string;
};

type GitStats = {
  branch?: string;
  filesTouched?: number;
  added?: number;
  removed?: number;
};

const STATE_KEY = "halyard.activeSession";

let status: vscode.StatusBarItem;

export function activate(context: vscode.ExtensionContext): void {
  status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
  status.command = "halyard.showCurrentScope";
  context.subscriptions.push(status);

  context.subscriptions.push(
    vscode.commands.registerCommand("halyard.startAIWork", () => startAIWork(context)),
    vscode.commands.registerCommand("halyard.stopAndRecordAIWork", () =>
      stopAndRecordAIWork(context),
    ),
    vscode.commands.registerCommand("halyard.recordAISession", () => recordAISession(context)),
    vscode.commands.registerCommand("halyard.openDashboard", () => openDashboard()),
    vscode.commands.registerCommand("halyard.showCurrentScope", () => showCurrentScope(context)),
    vscode.workspace.onDidChangeTextDocument(() => markActivity(context)),
    vscode.window.onDidChangeActiveTextEditor(() => markActivity(context)),
    vscode.window.onDidChangeWindowState((event) => {
      if (event.focused) {
        markActivity(context);
      }
    }),
  );

  updateStatus(context);

  // Recovery prompt: if a session was in progress when VS Code last quit, offer
  // to record it, continue tracking, or discard rather than silently losing it.
  const pending = context.workspaceState.get<SessionState>(STATE_KEY);
  if (pending) {
    const ageMinutes = Math.max(1, Math.round((Date.now() - pending.startedAt) / 60000));
    vscode.window
      .showWarningMessage(
        `Halyard found an unfinished VS Code session from ${ageMinutes}m ago.`,
        "Record it",
        "Continue tracking",
        "Discard",
      )
      .then((choice) => {
        if (choice === "Record it") {
          void stopAndRecordAIWork(context);
        } else if (choice === "Discard") {
          void context.workspaceState.update(STATE_KEY, undefined);
          updateStatus(context);
        }
        // "Continue tracking" or dismissed → leave state as-is
      });
  }
}

export function deactivate(): void {
  status?.dispose();
}

async function startAIWork(context: vscode.ExtensionContext): Promise<void> {
  const existing = context.workspaceState.get<SessionState>(STATE_KEY);
  if (existing) {
    vscode.window.showInformationMessage("Halyard is already tracking this VS Code AI session.");
    return;
  }

  const now = Date.now();
  const gitStats = await readGitStats();
  const state: SessionState = {
    startedAt: now,
    activeSeconds: 0,
    idleSeconds: 0,
    lastActivityAt: now,
    initialBranch: gitStats.branch,
  };
  await context.workspaceState.update(STATE_KEY, state);
  updateStatus(context);
  vscode.window.showInformationMessage("Halyard started tracking VS Code AI work.");
}

async function stopAndRecordAIWork(context: vscode.ExtensionContext): Promise<void> {
  markActivity(context);
  const state = context.workspaceState.get<SessionState>(STATE_KEY);
  if (!state) {
    vscode.window.showWarningMessage("No active Halyard VS Code session.");
    return;
  }

  const minutes = Math.max(1, Math.round((Date.now() - state.startedAt) / 60000));
  const gitStats = await readGitStats();
  const args = buildRecordArgs({
    minutes,
    branch: gitStats.branch ?? state.initialBranch,
    codeAdded: gitStats.added,
    codeRemoved: gitStats.removed,
    filesTouched: gitStats.filesTouched,
    humanActiveSeconds: state.activeSeconds,
    idleSeconds: state.idleSeconds,
  });

  try {
    await runHalyard(args);
    await context.workspaceState.update(STATE_KEY, undefined);
    updateStatus(context);
    vscode.window.showInformationMessage("Halyard recorded the VS Code AI session.");
  } catch (error) {
    vscode.window.showErrorMessage(`Halyard could not record the session: ${messageOf(error)}`);
  }
}

async function recordAISession(context: vscode.ExtensionContext): Promise<void> {
  const minutesRaw = await vscode.window.showInputBox({
    title: "Halyard: Record AI Session",
    prompt: "Minutes spent in this VS Code AI session",
    value: "15",
    validateInput: (value) => (Number(value) > 0 ? undefined : "Enter a positive number."),
  });
  if (!minutesRaw) {
    return;
  }
  const note = await vscode.window.showInputBox({
    title: "Halyard: Record AI Session",
    prompt: "Optional short note. Do not include prompts, code, or chat text.",
  });
  const gitStats = await readGitStats();
  const args = buildRecordArgs({
    minutes: Math.max(1, Math.round(Number(minutesRaw))),
    note,
    branch: gitStats.branch,
    codeAdded: gitStats.added,
    codeRemoved: gitStats.removed,
    filesTouched: gitStats.filesTouched,
  });

  try {
    await runHalyard(args);
    await context.workspaceState.update(STATE_KEY, undefined);
    updateStatus(context);
    vscode.window.showInformationMessage("Halyard recorded the VS Code AI session.");
  } catch (error) {
    vscode.window.showErrorMessage(`Halyard could not record the session: ${messageOf(error)}`);
  }
}

function openDashboard(): void {
  const executable = config().get<string>("executable", "halyard");
  const cwd = workspaceRoot();
  const child = spawn(executable, ["dashboard", "--open"], {
    cwd,
    detached: true,
    stdio: "ignore",
  });
  child.unref();
}

async function showCurrentScope(context: vscode.ExtensionContext): Promise<void> {
  const state = context.workspaceState.get<SessionState>(STATE_KEY);
  const cwd = workspaceRoot();
  const branch = (await readGitStats()).branch ?? "unknown";
  if (state) {
    const minutes = Math.max(1, Math.round((Date.now() - state.startedAt) / 60000));
    vscode.window.showInformationMessage(
      `Halyard tracking VS Code AI work for ${minutes}m in ${cwd} on ${branch}.`,
    );
  } else {
    vscode.window.showInformationMessage(`Halyard scope: ${cwd} on ${branch}.`);
  }
}

function markActivity(context: vscode.ExtensionContext): void {
  const state = context.workspaceState.get<SessionState>(STATE_KEY);
  if (!state) {
    return;
  }
  const now = Date.now();
  const idleAfter = config().get<number>("idleAfterSeconds", 300);
  const elapsed = Math.max(0, Math.round((now - state.lastActivityAt) / 1000));
  if (elapsed <= idleAfter) {
    state.activeSeconds += elapsed;
  } else {
    state.idleSeconds += elapsed;
  }
  state.lastActivityAt = now;
  void context.workspaceState.update(STATE_KEY, state);
  updateStatus(context);
}

function updateStatus(context: vscode.ExtensionContext): void {
  const state = context.workspaceState.get<SessionState>(STATE_KEY);
  if (state) {
    const minutes = Math.max(1, Math.round((Date.now() - state.startedAt) / 60000));
    status.text = `$(pulse) Halyard ${minutes}m`;
    status.tooltip = "Halyard is tracking VS Code AI work";
  } else {
    status.text = "$(record) Halyard";
    status.tooltip = "Start Halyard VS Code AI tracking";
  }
  status.show();
}

export function buildRecordArgs(options: {
  minutes: number;
  model?: string;
  note?: string;
  branch?: string;
  codeAdded?: number;
  codeRemoved?: number;
  filesTouched?: number;
  humanActiveSeconds?: number;
  idleSeconds?: number;
}): string[] {
  const model = options.model ?? config().get<string>("defaultModel", "github-copilot");
  const args = [
    "record-session",
    "--tool",
    "vscode",
    "--model",
    model,
    "--source",
    "vscode-extension",
    "--minutes",
    String(options.minutes),
  ];

  pushOptional(args, "--note", options.note);
  pushOptional(args, "--branch", options.branch);
  pushOptionalNumber(args, "--code-added", options.codeAdded);
  pushOptionalNumber(args, "--code-removed", options.codeRemoved);
  pushOptionalNumber(args, "--files-touched-count", options.filesTouched);
  pushOptionalNumber(args, "--human-active-seconds", options.humanActiveSeconds);
  pushOptionalNumber(args, "--idle-seconds", options.idleSeconds);
  args.push("--interaction-data-unavailable");
  args.push("--outcome-data-available");
  args.push("--telemetry-source", "vscode-extension");
  args.push("--telemetry-trust", "observed");
  return args;
}

function pushOptional(args: string[], flag: string, value?: string): void {
  if (value && value.trim()) {
    args.push(flag, value.trim());
  }
}

function pushOptionalNumber(args: string[], flag: string, value?: number): void {
  if (value !== undefined && Number.isFinite(value)) {
    args.push(flag, String(Math.max(0, Math.round(value))));
  }
}

function runHalyard(args: string[]): Promise<void> {
  const executable = config().get<string>("executable", "halyard");
  return new Promise((resolve, reject) => {
    execFile(executable, args, { cwd: workspaceRoot() }, (error, _stdout, stderr) => {
      if (error) {
        reject(new Error(stderr.trim() || error.message));
        return;
      }
      resolve();
    });
  });
}

async function readGitStats(): Promise<GitStats> {
  const cwd = workspaceRoot();
  const [branch, numstat] = await Promise.all([
    execGit(["branch", "--show-current"], cwd),
    execGit(["diff", "--numstat", "HEAD"], cwd),
  ]);
  const stats: GitStats = {
    branch: branch.trim() || undefined,
  };

  let files = 0;
  let added = 0;
  let removed = 0;
  for (const line of numstat.split(/\r?\n/)) {
    const parts = line.trim().split(/\s+/);
    if (parts.length < 3) {
      continue;
    }
    files += 1;
    added += numericPart(parts[0]);
    removed += numericPart(parts[1]);
  }
  stats.filesTouched = files;
  stats.added = added;
  stats.removed = removed;
  return stats;
}

function execGit(args: string[], cwd: string): Promise<string> {
  return new Promise((resolve) => {
    execFile("git", args, { cwd }, (_error, stdout) => resolve(stdout));
  });
}

export function numericPart(value: string): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function workspaceRoot(): string {
  return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? process.cwd();
}

function config(): vscode.WorkspaceConfiguration {
  return vscode.workspace.getConfiguration("halyard");
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
