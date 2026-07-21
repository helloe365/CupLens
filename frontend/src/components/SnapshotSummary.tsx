import { useMemo } from "react";

import { probabilityPercent } from "../api";
import type { Snapshot } from "../types";

interface SnapshotSummaryProps {
  snapshot: Snapshot;
}

const stageLabels: Record<string, string> = {
  round_of_32: "32 强",
  round_of_16: "16 强",
  quarterfinal: "四分之一决赛",
  semifinal: "半决赛",
  third_place: "三四名赛",
  final: "决赛",
};

function beijingDate(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Asia/Shanghai",
    hour12: false,
  }).format(new Date(value));
}

export function SnapshotSummary({ snapshot }: SnapshotSummaryProps) {
  const stats = useMemo(() => {
    const actualCount = snapshot.actual_matches.length;
    const forecastCount = snapshot.forecast_matches.length;

    const lastActual = snapshot.actual_matches
      .slice()
      .sort((left, right) =>
        right.kickoff_at.localeCompare(left.kickoff_at),
      )[0];
    const currentStage = lastActual
      ? (stageLabels[lastActual.stage] ?? lastActual.stage)
      : "尚未开赛";

    const leader = snapshot.team_probabilities
      .slice()
      .sort(
        (left, right) => right.champion_probability - left.champion_probability,
      )[0];

    const nextForecast = snapshot.forecast_matches
      .slice()
      .sort((left, right) =>
        left.kickoff_at.localeCompare(right.kickoff_at),
      )[0];

    return {
      actualCount,
      forecastCount,
      currentStage,
      leader,
      nextKickoff: nextForecast?.kickoff_at ?? null,
    };
  }, [snapshot]);

  return (
    <section
      className="panel snapshot-summary"
      aria-labelledby="summary-heading"
    >
      <div className="section-heading">
        <div>
          <p className="eyebrow">SNAPSHOT DIGEST</p>
          <h2 id="summary-heading">当前快照摘要</h2>
        </div>
        <span className="data-note">{snapshot.snapshot_id}</span>
      </div>

      <dl className="summary-grid">
        <div>
          <dt>已锁定真实赛果</dt>
          <dd>
            <strong>{stats.actualCount}</strong>
            <span>场</span>
          </dd>
        </div>
        <div>
          <dt>待赛预测</dt>
          <dd>
            <strong>{stats.forecastCount}</strong>
            <span>场</span>
          </dd>
        </div>
        <div>
          <dt>当前赛事阶段</dt>
          <dd>
            <strong>{stats.currentStage}</strong>
          </dd>
        </div>
        <div>
          <dt>夺冠概率领先</dt>
          <dd>
            {stats.leader ? (
              <>
                <strong>{stats.leader.team}</strong>
                <span>
                  {probabilityPercent(stats.leader.champion_probability)}
                </span>
              </>
            ) : (
              <strong>—</strong>
            )}
          </dd>
        </div>
        <div>
          <dt>下一场开球</dt>
          <dd>
            <strong>
              {stats.nextKickoff
                ? `${beijingDate(stats.nextKickoff)} CST`
                : "待定"}
            </strong>
          </dd>
        </div>
      </dl>
    </section>
  );
}
