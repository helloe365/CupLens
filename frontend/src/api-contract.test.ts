import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const frontendRoot = fileURLToPath(new URL("..", import.meta.url));

describe("API contract", () => {
  it("matches the FastAPI OpenAPI response schemas", () => {
    const result = spawnSync(
      process.execPath,
      ["scripts/api-contract.mjs", "--check"],
      { cwd: frontendRoot, encoding: "utf8" },
    );

    expect(result.status, `${result.stdout}\n${result.stderr}`).toBe(0);
  });
});
