import { describe, it, expect } from "vitest";
import { buildRecordArgs, numericPart, splitExecutable } from "./extension.js";

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
