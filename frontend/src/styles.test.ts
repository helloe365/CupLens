import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const styles = readFileSync(new URL("./styles.css", import.meta.url), "utf8");

describe("supporting typography", () => {
  it.each([
    ["eyebrow", ".eyebrow"],
    ["snapshot metadata label", ".model-badge dt"],
    ["pipeline stage label", ".pipeline-grid span"],
    ["source role", ".source-role"],
    ["boundary number", ".boundary-panel li::before"],
    ["dashboard step number", ".thesis-steps span"],
    ["agent capability number", ".agent-capabilities span"],
  ])("keeps the %s legible at 14px", (_label, selector) => {
    const escapedSelector = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    expect(styles).toMatch(new RegExp(`${escapedSelector}\\s*\\{[^}]*font(?:-size|):\\s*[^;}]*14px`, "s"));
  });
});
