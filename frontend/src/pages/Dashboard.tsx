import { useEffect, useState } from "react";

import { getLatestSnapshot } from "../api";
import { ChampionProbability } from "../components/ChampionProbability";
import { MatchCard, isPredictedMatch } from "../components/MatchCard";
import { ModelBadge } from "../components/ModelBadge";
import type { Snapshot } from "../types";

export function Dashboard() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    getLatestSnapshot()
      .then((data) => {
        if (active) setSnapshot(data);
      })
      .catch((reason: unknown) => {
        if (active) {
          setError(reason instanceof Error ? reason.message : "预测数据加载失败");
        }
      });
    return () => {
      active = false;
    };
  }, []);

  if (error) {
    return <div className="state-card state-card--error" role="alert">{error}</div>;
  }

  if (!snapshot) {
    return <div className="state-card state-card--loading">正在读取预计算快照…</div>;
  }

  if (snapshot.team_probabilities.length === 0 && snapshot.forecast_matches.length === 0) {
    return <div className="state-card">当前快照没有可展示的预测数据。</div>;
  }

  const ordered = [...snapshot.team_probabilities].sort(
    (left, right) => right.champion_probability - left.champion_probability,
  );
  const semifinalPredictions = snapshot.forecast_matches.filter(
    (match) => match.stage === "semifinal" && isPredictedMatch(match),
  );
  const likelyFinalists = [...snapshot.team_probabilities]
    .sort((left, right) => right.final_probability - left.final_probability)
    .slice(0, 2);

  return (
    <div className="page-stack">
      <section className="hero-grid">
        <div className="hero-copy">
          <p className="eyebrow">CURRENT FORECAST / 当前预测</p>
          <h1>答案会变化，证据不会。</h1>
          <p>
            已结束比赛锁定为真实赛果，未赛比赛只读取赛前快照。语言模型负责解释，
            不拥有任何概率写权限。
          </p>
        </div>
        {ordered[0] && (
          <div className="leader-card">
            <span>当前最可能冠军</span>
            <strong>{ordered[0].team}</strong>
            <small>数值见下方 API 原值卡片</small>
          </div>
        )}
      </section>

      <ModelBadge provenance={snapshot} />

      <div className="dashboard-grid">
        <ChampionProbability probabilities={snapshot.team_probabilities} />
        <aside className="panel final-callout">
          <p className="eyebrow">MOST LIKELY FINAL</p>
          <h2>最可能进入决赛的两队</h2>
          {likelyFinalists.length === 2 ? (
            <div className="final-pairing">
              <strong>{likelyFinalists[0].team}</strong>
              <span>×</span>
              <strong>{likelyFinalists[1].team}</strong>
            </div>
          ) : (
            <div className="state-card">决赛概率数据不足。</div>
          )}
          <p className="fine-print">
            此处按 API 返回的进决赛概率排序，不推断具体决赛对阵概率。
          </p>
          <div className="legend">
            <span><i className="legend-actual" /> ACTUAL 真实赛果</span>
            <span><i className="legend-forecast" /> FORECAST 模型预测</span>
          </div>
        </aside>
      </div>

      <section aria-labelledby="semifinal-heading">
        <div className="section-heading section-heading--outside">
          <div>
            <p className="eyebrow">NEXT MATCHES</p>
            <h2 id="semifinal-heading">两场半决赛</h2>
          </div>
          <span className="data-note">90 分钟概率 · 晋级概率 · xG · Top-3 比分</span>
        </div>
        {semifinalPredictions.length > 0 ? (
          <div className="match-grid">
            {semifinalPredictions.map((match) => (
              <MatchCard key={match.match_id} match={match} />
            ))}
          </div>
        ) : (
          <div className="state-card">当前快照没有半决赛预测。</div>
        )}
      </section>
    </div>
  );
}
