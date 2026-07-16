import type { SnapshotComparison } from "../types";
import { ProbabilityValue } from "./ProbabilityValue";

interface SnapshotDiffProps {
  comparison: SnapshotComparison;
}

export function SnapshotDiff({ comparison }: SnapshotDiffProps) {
  const changes = Object.entries(comparison.probability_changes).sort(
    ([left], [right]) => left.localeCompare(right),
  );

  return (
    <section className="panel diff-panel" aria-labelledby="diff-heading">
      <div className="section-heading">
        <div>
          <p className="eyebrow">不可覆盖快照对比</p>
          <h2 id="diff-heading">夺冠概率变化</h2>
        </div>
        <span className="data-note">
          {comparison.base_snapshot_id} → {comparison.target_snapshot_id}
        </span>
      </div>

      {changes.length === 0 ? (
        <div className="state-card">两个快照没有可比较的球队概率。</div>
      ) : (
        <div className="diff-list">
          {changes.map(([team, change]) => (
            <div className="diff-row" key={team}>
              <strong>{team}</strong>
              <span className={change > 0 ? "delta-up" : change < 0 ? "delta-down" : "delta-flat"}>
                {change > 0 ? "+" : ""}
                <ProbabilityValue value={Math.abs(change)} />
              </span>
            </div>
          ))}
        </div>
      )}

      <div className="actual-additions">
        <span>新增真实赛果</span>
        {comparison.added_actual_match_ids.length > 0 ? (
          <strong>{comparison.added_actual_match_ids.map((id) => `#${id}`).join("、")}</strong>
        ) : (
          <strong>无</strong>
        )}
      </div>
    </section>
  );
}
