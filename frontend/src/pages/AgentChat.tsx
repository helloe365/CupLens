import { type FormEvent, useState } from "react";

import { askAgent } from "../api";
import { ChampionProbability } from "../components/ChampionProbability";
import { MatchCard } from "../components/MatchCard";
import { ModelBadge } from "../components/ModelBadge";
import { SnapshotDiff } from "../components/SnapshotDiff";
import type {
  AgentStructuredData,
  ChatResponse,
  CurrentForecastResponse,
  MatchPredictionResponse,
  ModelCardResponse,
  SnapshotComparison,
} from "../types";

const suggestions = [
  "谁最可能夺冠？",
  "Spain 和 Argentina 的决赛预测是什么？",
  "比较最早与最新快照有什么变化？",
  "这个模型有哪些限制？",
];

function hasTeamProbabilities(
  data: AgentStructuredData,
): data is CurrentForecastResponse {
  return "team_probabilities" in data;
}

function hasPrediction(
  data: AgentStructuredData,
): data is MatchPredictionResponse {
  return "prediction" in data;
}

function isComparison(
  data: AgentStructuredData,
): data is SnapshotComparison {
  return "probability_changes" in data;
}

function isModelCard(data: AgentStructuredData): data is ModelCardResponse {
  return "model_card" in data;
}

function StructuredResult({ data }: { data: AgentStructuredData }) {
  if (hasTeamProbabilities(data)) {
    return (
      <div className="agent-structured">
        <ChampionProbability probabilities={data.team_probabilities} />
        <div className="match-grid">
          {data.forecast_matches.slice(0, 2).map((match) => (
            <MatchCard key={match.match_id} match={match} />
          ))}
        </div>
      </div>
    );
  }
  if (hasPrediction(data)) return <MatchCard match={data.prediction} />;
  if (isComparison(data)) return <SnapshotDiff comparison={data} />;
  if (isModelCard(data)) {
    return (
      <section className="panel limitations-card">
        <h3>模型限制</h3>
        {data.limitations.length > 0 ? (
          <ul>{data.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
        ) : (
          <div className="state-card">模型卡没有限制说明。</div>
        )}
      </section>
    );
  }
  return <div className="state-card">工具没有返回可识别的结构化数据。</div>;
}

export function AgentChat() {
  const [question, setQuestion] = useState(suggestions[0]);
  const [response, setResponse] = useState<ChatResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event?: FormEvent) {
    event?.preventDefault();
    const cleanQuestion = question.trim();
    if (!cleanQuestion) {
      setError("请输入一个问题。");
      return;
    }

    setLoading(true);
    setError(null);
    try {
      setResponse(await askAgent(cleanQuestion));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Agent 问答失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="page-stack">
      <section className="page-intro agent-intro">
        <div>
          <p className="eyebrow">READ-ONLY AGENT / 预测问答</p>
          <h1>它可以解释概率，但没有权力改写概率。</h1>
          <p>Agent 先调用四个白名单只读工具，再组织回答；结构化卡片始终是数值真源。</p>
        </div>
        <div className="agent-rule-card">
          <span>AGENT ACCESS</span>
          <strong>READ ONLY</strong>
          <small>无训练权限 · 无快照写权限 · 无概率计算权限</small>
        </div>
      </section>

      <section className="agent-console" aria-labelledby="agent-console-heading">
        <header>
          <div>
            <i aria-hidden="true" />
            <span id="agent-console-heading">CupLens evidence console</span>
          </div>
          <small>4 tools available</small>
        </header>
        <div className="suggestion-list" aria-label="建议问题">
          {suggestions.map((suggestion) => (
            <button
              key={suggestion}
              type="button"
              onClick={() => setQuestion(suggestion)}
            >
              {suggestion}
            </button>
          ))}
        </div>

        <form className="chat-form" onSubmit={submit}>
          <label htmlFor="agent-question">输入关于预测、比赛、快照或模型的问题</label>
          <div>
            <input
              autoComplete="off"
              id="agent-question"
              maxLength={1000}
              name="question"
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="例如：比较最早与最新快照的变化…"
              value={question}
            />
            <button disabled={loading} type="submit">
              {loading ? "正在读取证据…" : "发送问题"}
            </button>
          </div>
        </form>
      </section>

      {error && <div className="state-card state-card--error" role="alert">{error}</div>}
      {loading && <div className="state-card state-card--loading">正在读取确定性工具结果…</div>}

      {!loading && !response && !error && (
        <div className="agent-capabilities">
          <div><span>01</span><strong>当前预测</strong><p>读取冠军概率与剩余比赛。</p></div>
          <div><span>02</span><strong>比赛解释</strong><p>返回胜平负、晋级与比分分布。</p></div>
          <div><span>03</span><strong>快照比较</strong><p>解释概率如何随真实赛果变化。</p></div>
          <div><span>04</span><strong>模型边界</strong><p>说明方法、回测指标和已知限制。</p></div>
        </div>
      )}

      {response && !loading && (
        <section className="agent-answer" aria-live="polite">
          {response.mode === "template" && (
            <div className="fallback-banner" role="status">
              智能解释暂不可用，以下为模型结构化结果。
            </div>
          )}
          <div className="answer-copy">
            <span className={`mode-pill mode-pill--${response.mode}`}>
              {response.mode === "qwen" ? "QWEN EXPLANATION" : "TEMPLATE FALLBACK"}
            </span>
            <p>{response.answer}</p>
          </div>

          <div className="tool-trace">
            <span>只读工具调用</span>
            {response.tool_calls.length > 0 ? (
              response.tool_calls.map((call, index) => (
                <code key={`${call.name}-${index}`}>{call.name}</code>
              ))
            ) : (
              <strong>没有完成工具调用</strong>
            )}
          </div>

          {"snapshot_id" in response.structured_data ? (
            <ModelBadge provenance={response.structured_data} />
          ) : (
            <ModelBadge provenance={response.structured_data.target} />
          )}
          <StructuredResult data={response.structured_data} />
        </section>
      )}

      <p className="agent-disclaimer">
        仅解释已提交快照；不补全缺失概率，不提供博彩建议，也不会接收 API Key。
      </p>
    </div>
  );
}
