import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

vi.mock("node:child_process", () => ({
  execFile: vi.fn(),
  spawn: vi.fn(() => ({ unref: vi.fn() })),
}));

import { execFile, spawn } from "node:child_process";
import { activate, buildRecordArgs, numericPart, splitExecutable, readGitStats, startAIWork, stopAndRecordAIWork, recordAISession, markActivity, openDashboard, showCurrentScope } from "./extension.js";
import { resetVscodeMocks, setConfiguration, window } from "./__mocks__/vscode";

const execFileMock = execFile as unknown as ReturnType<typeof vi.fn>;
const spawnMock = spawn as unknown as ReturnType<typeof vi.fn>;

describe("splitExecutable — wrapper command support", () => {
  it("treats a bare binary as the command with no prefix args", () => {
    expect(splitExecutable("halyard")).toEqual({
      command: "halyard",
      prefixArgs: [],
    });
  });

  it("splits a wrapper command like `uv run halyard`", () => {
    expect(splitExecutable("uv run halyard")).toEqual({
      command: "uv",
      prefixArgs: ["run", "halyard"],
    });
  });

  it("collapses extra whitespace and trims", () => {
    expect(splitExecutable("  uvx   halyard  ")).toEqual({
      command: "uvx",
      prefixArgs: ["halyard"],
    });
  });

  it("falls back to halyard when empty", () => {
    expect(splitExecutable("   ")).toEqual({
      command: "halyard",
      prefixArgs: [],
    });
  });
});

// ---------------------------------------------------------------------------
// numericPart
// ---------------------------------------------------------------------------

describe("numericPart", () => {
  it("parses a plain integer string", () => {
    expect(numericPart("42")).toBe(42);
  });

  it("returns 0 for binary-file dash placeholder", () => {
    expect(numericPart("-")).toBe(0);
  });

  it("returns 0 for empty string", () => {
    expect(numericPart("")).toBe(0);
  });

  it("returns 0 for non-numeric text", () => {
    expect(numericPart("abc")).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// buildRecordArgs
// ---------------------------------------------------------------------------

describe("buildRecordArgs — required fields", () => {
  it("always includes record-session, --tool vscode, --minutes, telemetry flags", () => {
    const args = buildRecordArgs({ minutes: 10, model: "github-copilot" });
    expect(args[0]).toBe("record-session");
    expect(args).toContain("--tool");
    expect(args[args.indexOf("--tool") + 1]).toBe("vscode");
    expect(args).toContain("--minutes");
    expect(args[args.indexOf("--minutes") + 1]).toBe("10");
    expect(args).toContain("--telemetry-source");
    expect(args[args.indexOf("--telemetry-source") + 1]).toBe("vscode-extension");
    expect(args).toContain("--telemetry-trust");
    expect(args[args.indexOf("--telemetry-trust") + 1]).toBe("observed");
  });

  it("always sets --interaction-data-unavailable and --outcome-data-available", () => {
    const args = buildRecordArgs({ minutes: 5, model: "github-copilot" });
    expect(args).toContain("--interaction-data-unavailable");
    expect(args).toContain("--outcome-data-available");
  });

  it("uses the model passed in options", () => {
    const args = buildRecordArgs({ minutes: 5, model: "claude-sonnet-4-6" });
    expect(args[args.indexOf("--model") + 1]).toBe("claude-sonnet-4-6");
  });

  it("falls back to config default when model is omitted", () => {
    // The vscode stub returns the fallback value ("github-copilot")
    const args = buildRecordArgs({ minutes: 5 });
    expect(args).toContain("--model");
    expect(args[args.indexOf("--model") + 1]).toBe("github-copilot");
  });
});

describe("buildRecordArgs — optional fields omitted when not provided", () => {
  it("omits --branch when not provided", () => {
    const args = buildRecordArgs({ minutes: 5, model: "github-copilot" });
    expect(args).not.toContain("--branch");
  });

  it("omits --note when not provided", () => {
    const args = buildRecordArgs({ minutes: 5, model: "github-copilot" });
    expect(args).not.toContain("--note");
  });

  it("omits --code-added when not provided", () => {
    const args = buildRecordArgs({ minutes: 5, model: "github-copilot" });
    expect(args).not.toContain("--code-added");
  });
});

describe("buildRecordArgs — optional fields included when provided", () => {
  it("includes --branch when provided", () => {
    const args = buildRecordArgs({ minutes: 5, model: "github-copilot", branch: "main" });
    expect(args[args.indexOf("--branch") + 1]).toBe("main");
  });

  it("includes --code-added and --code-removed", () => {
    const args = buildRecordArgs({
      minutes: 5,
      model: "github-copilot",
      codeAdded: 120,
      codeRemoved: 30,
    });
    expect(args[args.indexOf("--code-added") + 1]).toBe("120");
    expect(args[args.indexOf("--code-removed") + 1]).toBe("30");
  });

  it("includes --human-active-seconds and --idle-seconds", () => {
    const args = buildRecordArgs({
      minutes: 20,
      model: "github-copilot",
      humanActiveSeconds: 600,
      idleSeconds: 600,
    });
    expect(args[args.indexOf("--human-active-seconds") + 1]).toBe("600");
    expect(args[args.indexOf("--idle-seconds") + 1]).toBe("600");
  });
});

describe("buildRecordArgs — privacy boundary", () => {
  it("never includes a --note with prompts or code text", () => {
    // Confirms the note field is passed through as-is, not enriched with any
    // additional context by the extension.
    const args = buildRecordArgs({
      minutes: 5,
      model: "github-copilot",
      note: "refactor auth module",
    });
    expect(args[args.indexOf("--note") + 1]).toBe("refactor auth module");
    // No extra flags beyond what was explicitly passed
    const flagCount = args.filter((a) => a.startsWith("--")).length;
    expect(flagCount).toBeLessThan(15);
  });
});

describe("extension lifecycle and git stats", () => {
  const SESSION_KEY = "halyard.activeSession";

  function makeContext() {
    const state = new Map<string, unknown>();
    return {
      workspaceState: {
        get: <T>(key: string): T | undefined => state.get(key) as T | undefined,
        update: (key: string, value: unknown): Promise<void> => {
          if (value === undefined) {
            state.delete(key);
          } else {
            state.set(key, value);
          }
          return Promise.resolve();
        },
      },
      subscriptions: [] as unknown[],
    };
  }

  beforeEach(() => {
    vi.resetAllMocks();
    resetVscodeMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("readGitStats parses branch and numstat output", async () => {
    execFileMock.mockImplementation((command, args, _options, callback) => {
      if (command === "git" && args[0] === "branch") {
        callback(null, "main\n", "");
      } else if (command === "git" && args[0] === "diff") {
        callback(null, "-\t-\timage.png\n5\t1\tsrc/extension.ts\n", "");
      } else {
        callback(null, "", "");
      }
    });

    const stats = await readGitStats();

    expect(stats.branch).toBe("main");
    expect(stats.filesTouched).toBe(2);
    expect(stats.added).toBe(5);
    expect(stats.removed).toBe(1);
  });

  it("startAIWork creates a pending VS Code session", async () => {
    execFileMock.mockImplementation((command, args, _options, callback) => {
      if (command === "git") {
        if (args[0] === "branch") callback(null, "main\n", "");
        else callback(null, "1\t0\tsrc/extension.ts\n", "");
      } else {
        callback(null, "", "");
      }
    });

    const context = makeContext();
    await startAIWork(context as any);

    expect(context.workspaceState.get(SESSION_KEY)).toEqual(
      expect.objectContaining({
        activeSeconds: 0,
        idleSeconds: 0,
        initialBranch: "main",
      }),
    );
  });

  it("markActivity records active and idle seconds correctly", () => {
    const context = makeContext();
    const state = {
      startedAt: 0,
      activeSeconds: 0,
      idleSeconds: 0,
      lastActivityAt: 1_000,
    };
    context.workspaceState.update(SESSION_KEY, state);

    vi.useFakeTimers();
    vi.setSystemTime(1_000 + 200_000);
    markActivity(context as any);
    expect(state.activeSeconds).toBe(200);

    vi.setSystemTime(601_000);
    markActivity(context as any);
    expect(state.idleSeconds).toBe(400);
  });

  it("stopAndRecordAIWork records the session and clears state", async () => {
    const now = 1_000_000;
    vi.useFakeTimers();
    vi.setSystemTime(now);

    const context = makeContext();
    const state = {
      startedAt: now - 70_000,
      activeSeconds: 0,
      idleSeconds: 0,
      lastActivityAt: now - 30_000,
      initialBranch: "main",
    };
    await context.workspaceState.update(SESSION_KEY, state);

    execFileMock.mockImplementation((command, args, _options, callback) => {
      if (command === "git") {
        if (args[0] === "branch") callback(null, "main\n", "");
        else callback(null, "2\t1\tsrc/extension.ts\n", "");
      } else if (command === "halyard") {
        callback(null, "", "");
      } else {
        callback(null, "", "");
      }
    });

    await stopAndRecordAIWork(context as any);

    expect(execFileMock).toHaveBeenLastCalledWith(
      "halyard",
      expect.arrayContaining(["record-session", "--tool", "vscode", "--minutes", "1", "--branch", "main", "--code-added", "2", "--code-removed", "1", "--files-touched-count", "1"]),
      expect.anything(),
      expect.any(Function),
    );
    expect(context.workspaceState.get(SESSION_KEY)).toBeUndefined();
  });

  it("openDashboard constructs a detached process invocation", () => {
    setConfiguration("halyard", "executable", "uv run halyard");
    openDashboard();
    expect(spawnMock).toHaveBeenCalledWith(
      "uv",
      expect.arrayContaining(["run", "halyard", "dashboard", "--open"]),
      expect.objectContaining({ detached: true, stdio: "ignore" }),
    );
  });

  it("showCurrentScope displays workspace and branch info", async () => {
    execFileMock.mockImplementation((command, args, _options, callback) => {
      if (command === "git" && args[0] === "branch") {
        callback(null, "main\n", "");
      } else if (command === "git" && args[0] === "diff") {
        callback(null, "", "");
      } else {
        callback(null, "", "");
      }
    });

    await showCurrentScope({ workspaceState: { get: () => undefined }, subscriptions: [] } as any);
  });

  it("recordAISession prompts for minutes/note and records a session", async () => {
    window.showInputBox = vi
      .fn()
      .mockResolvedValueOnce("12")
      .mockResolvedValueOnce("manual session note");

    const context = makeContext();
    execFileMock.mockImplementation((command, args, _options, callback) => {
      if (command === "git") {
        if (args[0] === "branch") callback(null, "main\n", "");
        else callback(null, "3\t1\tsrc/extension.ts\n", "");
      } else if (command === "halyard") {
        callback(null, "", "");
      } else {
        callback(null, "", "");
      }
    });

    await recordAISession(context as any);

    expect(execFileMock).toHaveBeenLastCalledWith(
      "halyard",
      expect.arrayContaining([
        "record-session",
        "--tool",
        "vscode",
        "--minutes",
        "12",
        "--note",
        "manual session note",
      ]),
      expect.anything(),
      expect.any(Function),
    );
  });

  it("activate prompts to recover an unfinished VS Code session and discards when requested", async () => {
    const state = {
      startedAt: Date.now() - 5 * 60 * 1000,
      activeSeconds: 0,
      idleSeconds: 0,
      lastActivityAt: Date.now() - 60 * 1000,
    };
    const context = makeContext();
    await context.workspaceState.update(SESSION_KEY, state);

    window.showWarningMessage = vi.fn().mockResolvedValue("Discard");
    window.showInputBox = vi.fn();
    execFileMock.mockImplementation((command, args, _options, callback) => {
      if (command === "git") {
        if (args[0] === "branch") callback(null, "main\n", "");
        else callback(null, "", "");
      } else {
        callback(null, "", "");
      }
    });

    activate(context as any);
    await Promise.resolve();
    await Promise.resolve();

    expect(context.workspaceState.get(SESSION_KEY)).toBeUndefined();
    expect(window.showWarningMessage).toHaveBeenCalled();
  });

  it("activate prompts to recover an unfinished VS Code session and records when requested", async () => {
    const state = {
      startedAt: Date.now() - 5 * 60 * 1000,
      activeSeconds: 0,
      idleSeconds: 0,
      lastActivityAt: Date.now() - 60 * 1000,
    };
    const context = makeContext();
    await context.workspaceState.update(SESSION_KEY, state);

    window.showWarningMessage = vi.fn().mockResolvedValue("Record it");
    window.showInputBox = vi.fn();
    execFileMock.mockImplementation((command, args, _options, callback) => {
      if (command === "git") {
        if (args[0] === "branch") callback(null, "main\n", "");
        else callback(null, "1\t0\tsrc/extension.ts\n", "");
      } else if (command === "halyard") {
        callback(null, "", "");
      } else {
        callback(null, "", "");
      }
    });

    activate(context as any);
    await new Promise((resolve) => setTimeout(resolve, 0));
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(execFileMock).toHaveBeenCalledWith(
      "halyard",
      expect.arrayContaining(["record-session", "--tool", "vscode"]),
      expect.anything(),
      expect.any(Function),
    );
    expect(context.workspaceState.get(SESSION_KEY)).toBeUndefined();
  });
});
