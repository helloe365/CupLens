import { useEffect, useState } from "react";

import { compareSnapshots, getLatestSnapshot, getSnapshots } from "../api";
import { Bracket } from "../components/Bracket";
import { ModelBadge } from "../components/ModelBadge";
import { SnapshotDiff } from "../components/SnapshotDiff";
import type { Snapshot, SnapshotComparison, SnapshotIndexEntry } from "../types";

interface TimelineData {
  snapshot: Snapshot;
  index: SnapshotIndexEntry[];
}

export function Timeline() {
  const [data, setData] = useState<TimelineData | null>(null);
  const [comparison, setComparison] = useState<SnapshotComparison | null>(null);
  const [baseId, setBaseId] = useState("");
  const [targetId, setTargetId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [comparisonError, setComparisonError] = useState<string | null>(null);
  const [comparing, setComparing] = useState(false);

  useEffect(() => {
    let active = true;
    Promise.all([getLatestSnapshot(), getSnapshots()])
      .then(([snapshot, index]) => {
        if (!active) return;
        setData({ snapshot, index });
        if (index.length > 0) {
          setBaseId(index[0].snapshot_id);
          setTargetId(index[index.length - 1].snapshot_id);
        }
      })
      .catch((reason: unknown) => {
        if (active) {
          setError(reason instanceof Error ? reason.message : "赛程数据加载失败");
        }
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!baseId || !targetId) return;
    let active = true;
    setComparing(true);
    setComparisonError(null);
    compareSnapshots(baseId, targetId)
      .then((result) => {
        if (active) setComparison(result);
      })
      .catch((reason: unknown) => {
        if (active) {
          setComparisonError(
            reason instanceof Error ? reason.message : "快照比较失败",
          );
        }
      })
      .finally(() => {
        if (active) setComparing(false);
      });
    return () => {
      active = false;
    };
  }, [baseId, targetId]);

  if (error) {
    return <div className="state-card state-card--error" role="alert">{error}</div>;
  }
  if (!data) {
    return <div className="state-card state-card--loading">正在读取赛程与快照索引…</div>;
  }

  return (
    <div className="page-stack">
      <section className="page-intro">
        <p className="eyebrow">TIMELINE / 赛程与变化</p>
        <h1>真实比分向前锁定，预测沿时间留痕。</h1>
        <p>比赛 ID 明确连接每轮赛程；快照只新增，不覆盖。</p>
      </section>

      <ModelBadge provenance={data.snapshot} />

      <section className="panel group-summary" aria-labelledby="group-heading">
        <div className="section-heading">
          <div>
            <p className="eyebrow">GROUP STAGE</p>
            <h2 id="group-heading">小组赛最终排名摘要</h2>
          </div>
          <span className="kind-label kind-label--actual">ACTUAL · 已锁定</span>
        </div>
        <div className="state-card">
          当前只读快照 API 未提供分组排名明细；前端不会从淘汰赛结果反推或补全。
        </div>
      </section>

      <section aria-labelledby="bracket-heading">
        <div className="section-heading section-heading--outside">
          <div>
            <p className="eyebrow">KNOCKOUT BRACKET</p>
            <h2 id="bracket-heading">32 强至决赛</h2>
          </div>
          <div className="legend legend--inline">
            <span><i className="legend-actual" /> 真实比分</span>
            <span><i className="legend-forecast" /> 模型预测</span>
          </div>
        </div>
        <Bracket
          actualMatches={data.snapshot.actual_matches}
          forecastMatches={data.snapshot.forecast_matches}
        />
      </section>

      <section className="snapshot-controls" aria-labelledby="compare-heading">
        <div>
          <p className="eyebrow">SNAPSHOT CHANGE</p>
          <h2 id="compare-heading">选择两个证据时点</h2>
        </div>
        {data.index.length === 0 ? (
          <div className="state-card">快照索引为空，无法比较。</div>
        ) : (
          <div className="select-grid">
            <label>
              基准快照
              <select value={baseId} onChange={(event) => setBaseId(event.target.value)}>
                {data.index.map((entry) => (
                  <option key={entry.snapshot_id} value={entry.snapshot_id}>
                    {entry.snapshot_id}
                  </option>
                ))}
              </select>
            </label>
            <span aria-hidden="true">→</span>
            <label>
              目标快照
              <select value={targetId} onChange={(event) => setTargetId(event.target.value)}>
                {data.index.map((entry) => (
                  <option key={entry.snapshot_id} value={entry.snapshot_id}>
                    {entry.snapshot_id}
                  </option>
                ))}
              </select>
            </label>
          </div>
        )}
      </section>

      {comparing ? (
        <div className="state-card state-card--loading">正在比较两个快照…</div>
      ) : comparisonError ? (
        <div className="state-card state-card--error" role="alert">{comparisonError}</div>
      ) : comparison ? (
        <SnapshotDiff comparison={comparison} />
      ) : null}
    </div>
  );
}
