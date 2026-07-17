import { useEffect, useState } from "react";

import { getLatestSnapshot } from "../api";
import { ChampionProbability } from "../components/ChampionProbability";
import { MatchCard, isPredictedMatch } from "../components/MatchCard";
import { ModelBadge } from "../components/ModelBadge";
import { ProbabilityValue } from "../components/ProbabilityValue";
import type { Snapshot } from "../types";

function shortDate(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "long",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Asia/Shanghai",
    hour12: false,
  }).format(new Date(value));
}

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
  const remainingPredictions = snapshot.forecast_matches
    .filter(isPredictedMatch)
    .sort((left, right) => new Date(left.kickoff_at).getTime() - new Date(right.kickoff_at).getTime());
  const finalPrediction = remainingPredictions.find((match) => match.stage === "final");
  const actualCount = snapshot.actual_matches.length;
  const sourceCount = snapshot.sources.length;

  return (
    <div className="page-stack">
      <section className="showcase-hero">
        <div className="hero-copy">
          <div className="hero-status">
            <span><i /> 最新快照已验证</span>
            <span>数据截止 {shortDate(snapshot.cutoff_at)} CST</span>
          </div>
          <p className="eyebrow">WORLD CUP 2026 · FORECAST CONTROL ROOM</p>
          <h1>把每一次冠军预测，<em>钉在它发生的时间上。</em></h1>
          <p>
            CupLens 用确定性模型计算概率，用不可覆盖快照保存证据，再让 Agent
            解释变化。评审看到的每一个数字，都能追溯到数据截止时间与模型版本。
          </p>
          <div className="hero-actions">
            <a className="primary-action" href="#/agent">
              直接询问 Agent <span aria-hidden="true">→</span>
            </a>
            <a className="text-action" href="#/timeline">
              查看完整淘汰赛
            </a>
          </div>
        </div>

        {ordered.length > 0 && (
          <aside className="forecast-ticket" aria-label="当前冠军预测">
            <header>
              <span>CHAMPION RACE</span>
              <span>FINAL / NEW YORK</span>
            </header>
            <div className="ticket-leader">
              <span>模型当前领跑</span>
              <strong>{ordered[0].team}</strong>
              <ProbabilityValue value={ordered[0].champion_probability} />
            </div>
            <div className="race-bars">
              {ordered.map((item, index) => (
                <div className="race-row" key={item.team}>
                  <span>{item.team}</span>
                  <div aria-hidden="true">
                    <i
                      className={index === 0 ? "race-fill race-fill--leader" : "race-fill"}
                      style={{ width: `${item.champion_probability * 100}%` }}
                    />
                  </div>
                  <ProbabilityValue value={item.champion_probability} />
                </div>
              ))}
            </div>
            {finalPrediction && (
              <footer>
                <span>决赛对阵</span>
                <strong>{finalPrediction.home_team} <i>VS</i> {finalPrediction.away_team}</strong>
              </footer>
            )}
          </aside>
        )}
      </section>

      <section className="evidence-rail" aria-label="预测可信信息">
        <div><span>已锁定真实赛果</span><strong>{actualCount} 场</strong></div>
        <div><span>蒙特卡洛模拟</span><strong>{snapshot.iterations.toLocaleString("zh-CN")} 次</strong></div>
        <div><span>核验数据来源</span><strong>{sourceCount} 个</strong></div>
        <div><span>Agent 权限</span><strong>4 个只读工具</strong></div>
      </section>

      <ModelBadge provenance={snapshot} />

      <div className="dashboard-grid">
        <ChampionProbability probabilities={snapshot.team_probabilities} />
        <aside className="panel thesis-panel">
          <p className="eyebrow">WHY CUPLENS</p>
          <h2>概率之外，更重要的是预测的来路。</h2>
          <div className="thesis-steps">
            <div><span>01</span><p><strong>计算</strong> Elo、Poisson 与 Dixon–Coles 生成赛果分布。</p></div>
            <div><span>02</span><p><strong>冻结</strong> 数据、参数、随机种子与结果写入快照。</p></div>
            <div><span>03</span><p><strong>解释</strong> Agent 只读工具结果，不重新创造概率。</p></div>
          </div>
          <a className="inline-action" href="#/evidence">
            检查模型与证据 <span aria-hidden="true">→</span>
          </a>
        </aside>
      </div>

      <section aria-labelledby="next-heading">
        <div className="section-heading section-heading--outside">
          <div>
            <p className="eyebrow">MATCH INTELLIGENCE</p>
            <h2 id="next-heading">剩余赛程预测</h2>
          </div>
          <span className="data-note">胜平负 · 晋级概率 · 预期进球 · Top-3 比分</span>
        </div>
        {remainingPredictions.length > 0 ? (
          <div className="match-grid">
            {remainingPredictions.map((match) => (
              <MatchCard key={match.match_id} match={match} />
            ))}
          </div>
        ) : (
          <div className="state-card">当前快照中的比赛已经全部结束。</div>
        )}
      </section>

      <section className="experience-section" aria-labelledby="experience-heading">
        <div className="section-heading section-heading--outside">
          <div>
            <p className="eyebrow">EXPLORE THE SYSTEM</p>
            <h2 id="experience-heading">不止一个预测结果</h2>
          </div>
          <span className="data-note">从赛程、证据到自然语言解释</span>
        </div>
        <div className="experience-grid">
          <a className="experience-card experience-card--pitch" href="#/timeline">
            <span>完整赛事路径</span>
            <strong>从 32 强走到决赛</strong>
            <p>真实比分与未来预测在同一张淘汰赛图中分层展示。</p>
            <i aria-hidden="true">打开淘汰赛 →</i>
          </a>
          <a className="experience-card experience-card--evidence" href="#/evidence">
            <span>可复核模型</span>
            <strong>查看回测与来源账本</strong>
            <p>模型流水线、时间切分指标、数据来源和限制集中呈现。</p>
            <i aria-hidden="true">打开证据中心 →</i>
          </a>
          <a className="experience-card experience-card--agent" href="#/agent">
            <span>只读预测 Agent</span>
            <strong>用问题探索结构化结果</strong>
            <p>询问冠军、比赛概率、快照变化或模型边界。</p>
            <i aria-hidden="true">开始提问 →</i>
          </a>
        </div>
      </section>
    </div>
  );
}
