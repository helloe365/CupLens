import { useEffect, useState } from "react";

import { compareSnapshots, getLatestSnapshot, getSnapshot, getSnapshots } from "../api";
import { Bracket } from "../components/Bracket";
import { ForecastBreakdown } from "../components/ForecastBreakdown";
import { ModelBadge } from "../components/ModelBadge";
import { SnapshotDiff } from "../components/SnapshotDiff";
import { SnapshotSummary } from "../components/SnapshotSummary";
import { SnapshotTimeline } from "../components/SnapshotTimeline";
import { TeamProbabilityBoard } from "../components/TeamProbabilityBoard";
import type { Snapshot, SnapshotComparison, SnapshotIndexEntry } from "../types";

const tournamentStages = [
  ["round_of_32", "32 强"],
  ["round_of_16", "16 强"],
  ["quarterfinal", "四分之一决赛"],
  ["semifinal", "半决赛"],
  ["final", "决赛"],
] as const;

export function Timeline() {
  const [index, setIndex] = useState<SnapshotIndexEntry[]>([]);
  const [latest, setLatest] = useState<Snapshot | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [selected, setSelected] = useState<Snapshot | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [comparison, setComparison] = useState<SnapshotComparison | null>(null);
  const [baseId, setBaseId] = useState("");
  const [targetId, setTargetId] = useState("");
  const [comparisonError, setComparisonError] = useState<string | null>(null);
  const [comparing, setComparing] = useState(false);

  useEffect(() => {
    let active = true;
    Promise.all([getLatestSnapshot(), getSnapshots()])
      .then(([snapshot, indexEntries]) => {
        if (!active) return;
        setLatest(snapshot);
        setIndex(indexEntries);
        setSelectedId(snapshot.snapshot_id);
        setSelected(snapshot);
        if (indexEntries.length > 0) {
          setBaseId(indexEntries[0].snapshot_id);
          setTargetId(indexEntries[indexEntries.length - 1].snapshot_id);
        }
      })
      .catch((reason: unknown) => {
        if (active) {
          setLoadError(reason instanceof Error ? reason.message : "赛程数据加载失败");
        }
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    if (latest && selectedId === latest.snapshot_id) {
      setSelected(latest);
      return;
    }
    let active = true;
    setLoadError(null);
    getSnapshot(selectedId)
      .then((snapshot) => {
        if (active) setSelected(snapshot);
      })
      .catch((reason: unknown) => {
        if (active) {
          setLoadError(reason instanceof Error ? reason.message : "历史快照加载失败");
        }
      });
    return () => {
      active = false;
    };
  }, [selectedId, latest]);

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

  if (loadError && !selected) {
    return <div className="state-card state-card--error" role="alert">{loadError}</div>;
  }
  if (!selected) {
    return <div className="state-card state-card--loading">正在读取赛程与快照索引…</div>;
  }

  return (
    <div className="page-stack">
      <section className="page-intro">
        <div>
          <p className="eyebrow">TOURNAMENT / 淘汰赛</p>
          <h1 className="timeline-title">一条从真实赛果，通往下一场预测的路。</h1>
          <p>每场比赛都保留明确 ID 与状态；已结束的比分向前锁定，未开赛的概率读取自当前快照。</p>
        </div>
      </section>

      <SnapshotTimeline
        entries={index}
        selectedId={selectedId}
        onSelect={setSelectedId}
      />

      <ModelBadge provenance={selected} />

      <SnapshotSummary snapshot={selected} />

      <TeamProbabilityBoard snapshot={selected} />

      <section className="tournament-progress" aria-labelledby="progress-heading">
        <div className="progress-heading">
          <div>
            <p className="eyebrow">TOURNAMENT PULSE</p>
            <h2 id="progress-heading">赛事进度</h2>
          </div>
          <div className="progress-total">
            <strong>{selected.actual_matches.length}</strong>
            <span>场淘汰赛已锁定</span>
          </div>
        </div>
        <ol>
          {tournamentStages.map(([stage, label]) => {
            const actual = selected.actual_matches.filter((match) => match.stage === stage).length;
            const forecast = selected.forecast_matches.filter((match) => match.stage === stage).length;
            const status = forecast > 0 ? "forecast" : actual > 0 ? "actual" : "pending";
            return (
              <li className={`progress-stage progress-stage--${status}`} key={stage}>
                <i aria-hidden="true" />
                <span>{label}</span>
                <strong>{forecast > 0 ? `${forecast} 场待赛` : actual > 0 ? `${actual} 场完成` : "待定"}</strong>
              </li>
            );
          })}
        </ol>
      </section>

      <section aria-labelledby="bracket-heading">
        <div className="section-heading section-heading--outside">
          <div>
            <p className="eyebrow">KNOCKOUT BRACKET</p>
            <h2 id="bracket-heading">完整比赛路径</h2>
          </div>
          <div className="legend legend--inline">
            <span><i className="legend-actual" /> 真实比分</span>
            <span><i className="legend-forecast" /> 模型预测</span>
          </div>
        </div>
        <Bracket
          actualMatches={selected.actual_matches}
          forecastMatches={selected.forecast_matches}
        />
      </section>

      <ForecastBreakdown snapshot={selected} />

      <section className="snapshot-controls" aria-labelledby="compare-heading">
        <div>
          <p className="eyebrow">SNAPSHOT CHANGE</p>
          <h2 id="compare-heading">选择两个证据时点</h2>
        </div>
        {index.length === 0 ? (
          <div className="state-card">快照索引为空，无法比较。</div>
        ) : (
          <div className="select-grid">
            <label>
              基准快照
              <select value={baseId} onChange={(event) => setBaseId(event.target.value)}>
                {index.map((entry) => (
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
                {index.map((entry) => (
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
