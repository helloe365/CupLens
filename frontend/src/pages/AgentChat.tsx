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
  "France 和 Spain 的半决赛预测是什么？",
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
        <p className="eyebrow">AGENT Q&A / 工具问答</p>
        <h1>让语言解释证据，不让语言改写数字。</h1>
        <p>Agent 只能调用四个白名单只读工具；结构化卡片始终优先于聊天文本。</p>
      </section>

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
        <label htmlFor="agent-question">向 CupLens 提问</label>
        <div>
          <input
            id="agent-question"
            maxLength={1000}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="例如：谁最可能夺冠？"
            value={question}
          />
          <button disabled={loading} type="submit">
            {loading ? "正在调用工具…" : "发送问题"}
          </button>
        </div>
      </form>

      {error && <div className="state-card state-card--error" role="alert">{error}</div>}
      {loading && <div className="state-card state-card--loading">正在读取确定性工具结果…</div>}

      {!loading && !response && !error && (
        <div className="state-card">选择建议问题或输入问题，结构化结果将在这里显示。</div>
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
