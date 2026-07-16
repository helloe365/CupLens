import { afterEach, describe, expect, it, vi } from "vitest";

import { getLatestSnapshot, probabilityPercent } from "./api";

describe("probabilityPercent", () => {
  it("formats model probability without changing the underlying value", () => {
    const probability = 0.1534;

    expect(probabilityPercent(probability)).toBe("15.3%");
    expect(probability).toBe(0.1534);
  });

  it("rejects a non-numeric probability received at runtime", () => {
    expect(() => probabilityPercent(null as unknown as number)).toThrow(
      "invalid probability",
    );
  });
});

describe("getLatestSnapshot", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("preserves probabilities and provenance returned by the API", async () => {
    const payload = {
      snapshot_id: "snapshot-v1",
      cutoff_at: "2026-07-14T11:25:41+08:00",
      generated_at: "2026-07-14T14:30:11+08:00",
      model_version: "elo-poisson-v1",
      data_sha256: "a".repeat(64),
      random_seed: 20260713,
      iterations: 20000,
      sources: [],
      actual_matches: [],
      forecast_matches: [],
      team_probabilities: [
        {
          team: "France",
          champion_probability: 0.1534,
          final_probability: 0.4,
        },
      ],
      metrics: {},
      limitations: [],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(payload), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    const result = await getLatestSnapshot();

    expect(result).toEqual(payload);
    expect(result.team_probabilities[0].champion_probability).toBe(0.1534);
  });

  it("returns a Chinese error when the API is unavailable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("unavailable", { status: 503 })),
    );

    await expect(getLatestSnapshot()).rejects.toThrow(
      "暂时无法读取预测数据（HTTP 503）",
    );
  });
});
