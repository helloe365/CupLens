import { useEffect, useState } from "react";

import { getLatestSnapshot } from "../api";
import { ModelBadge } from "../components/ModelBadge";
import type { Snapshot } from "../types";

const pipeline = [
  { label: "强弱基线", name: "时间衰减 Elo", copy: "衡量国家队长期实力，并降低久远比赛的影响。" },
  { label: "比分分布", name: "Poisson 矩阵", copy: "枚举 0–7 球比分，生成胜、平、负与 xG。" },
  { label: "低比分修正", name: "Dixon–Coles", copy: "修正 0:0、1:0、0:1、1:1 等相关比分。" },
  { label: "模型选择", name: "LightGBM 实验", copy: "用严格时间切分决定是否融合，不虚构模型增益。" },
  { label: "赛事推演", name: "20,000 次模拟", copy: "固定随机种子，预计算晋级与夺冠概率。" },
];

const limitationTranslations: Record<string, string> = {
  "Independent Poisson score model with scores truncated to 0-7.": "Poisson 比分模型假设双方进球相互独立，并将比分截断在 0–7 球。",
  "Advancement uses an Elo allocation for drawn score-matrix outcomes; it is not an exact extra-time or penalty model.": "平局后的晋级概率使用 Elo 分配，不是精确的加时赛或点球模型。",
  "Lineups, injuries, suspensions, weather, news, and player-level data are not modeled.": "暂未纳入首发、伤停、天气、新闻与球员级数据。",
  "Predictions are uncertain estimates and are not betting advice.": "所有预测均为不确定性估计，不构成博彩建议。",
};

function sourceLabel(sourceId: string): string {
  return sourceId
    .split("-")
    .map((part) => part.toUpperCase() === "FIFA" ? "FIFA" : part)
    .join(" ");
}

function domain(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

export function Evidence() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    getLatestSnapshot()
      .then((data) => {
        if (active) setSnapshot(data);
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : "模型证据加载失败");
      });
    return () => {
      active = false;
    };
  }, []);

  if (error) return <div className="state-card state-card--error" role="alert">{error}</div>;
  if (!snapshot) return <div className="state-card state-card--loading">正在读取模型与来源证据…</div>;

  const backtests = snapshot.metrics.results ?? [];
  const officialSources = snapshot.sources.filter((source) => source.role === "official").length;

  return (
    <div className="page-stack">
      <section className="page-intro evidence-intro">
        <div>
          <p className="eyebrow">MODEL & EVIDENCE / 模型与证据</p>
          <h1>一张预测，应该带着自己的说明书。</h1>
          <p>从数据截止、算法流水线到回测指标和来源链接，这里展示 CupLens 如何得到数字，以及数字没有覆盖什么。</p>
        </div>
        <div className="evidence-seal" aria-label="当前快照摘要">
          <span>VERIFIED SNAPSHOT</span>
          <strong>{snapshot.sources.length}</strong>
          <small>个核验来源 · {officialSources} 个官方来源</small>
        </div>
      </section>

      <ModelBadge provenance={snapshot} />

      <section aria-labelledby="pipeline-heading">
        <div className="section-heading section-heading--outside">
          <div>
            <p className="eyebrow">DETERMINISTIC PIPELINE</p>
            <h2 id="pipeline-heading">概率由模型计算，不由大模型生成</h2>
          </div>
          <span className="data-note">固定输入 · 固定参数 · 固定随机种子</span>
        </div>
        <ol className="pipeline-grid">
          {pipeline.map((stage, index) => (
            <li key={stage.name}>
              <span>{String(index + 1).padStart(2, "0")} · {stage.label}</span>
              <strong>{stage.name}</strong>
              <p>{stage.copy}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="backtest-section" aria-labelledby="backtest-heading">
        <div className="backtest-copy">
          <p className="eyebrow">TIME-SPLIT BACKTEST</p>
          <h2 id="backtest-heading">只用比赛发生前的数据</h2>
          <p>2018 与 2022 世界杯分别作为时间外测试集。特征截止时间严格早于测试赛事首场比赛，避免把未来信息泄漏进模型。</p>
          <code>
            回测基线：{String(snapshot.metrics.model_version ?? "未标注")}<br />
            截止规则：{String(snapshot.metrics.feature_cutoff_rule ?? "feature time < match time")}
          </code>
        </div>
        <div className="backtest-results">
          {backtests.length > 0 ? backtests.map((result) => (
            <article key={result.test_year}>
              <header><strong>{result.test_year}</strong><span>{result.matches} 场测试</span></header>
              <dl>
                <div><dt>准确率</dt><dd>{(result.accuracy * 100).toFixed(1)}%</dd></div>
                <div><dt>Brier</dt><dd>{result.brier_score.toFixed(3)}</dd></div>
                <div><dt>Log Loss</dt><dd>{result.log_loss.toFixed(3)}</dd></div>
              </dl>
            </article>
          )) : <div className="state-card">当前快照未包含回测结果。</div>}
        </div>
      </section>

      <div className="evidence-columns">
        <section className="panel source-ledger" aria-labelledby="source-heading">
          <div className="section-heading">
            <div>
              <p className="eyebrow">SOURCE LEDGER</p>
              <h2 id="source-heading">来源账本</h2>
            </div>
            <span className="data-note">可直接复核</span>
          </div>
          <div className="source-list">
            {snapshot.sources.map((source) => (
              <a href={source.url} key={source.source_id}>
                <span className={`source-role source-role--${source.role}`}>
                  {source.role === "official" ? "官方" : "交叉验证"}
                </span>
                <strong>{sourceLabel(source.source_id)}</strong>
                <small>{domain(source.url)} <i aria-hidden="true">↗</i></small>
              </a>
            ))}
          </div>
        </section>

        <section className="panel boundary-panel" aria-labelledby="boundary-heading">
          <div className="section-heading">
            <div>
              <p className="eyebrow">KNOWN BOUNDARIES</p>
              <h2 id="boundary-heading">主动说明限制</h2>
            </div>
          </div>
          <ul>
            {snapshot.limitations.map((item) => (
              <li key={item}>{limitationTranslations[item] ?? item}</li>
            ))}
          </ul>
          <div className="hash-card">
            <span>DATA SHA-256</span>
            <code title={snapshot.data_sha256}>{snapshot.data_sha256}</code>
            <small>任何数据变化都会生成不同指纹</small>
          </div>
        </section>
      </div>
    </div>
  );
}
