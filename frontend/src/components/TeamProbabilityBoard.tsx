import { useMemo } from "react";

import type { Snapshot } from "../types";
import { ProbabilityValue } from "./ProbabilityValue";

interface TeamProbabilityBoardProps {
  snapshot: Snapshot;
}

export function TeamProbabilityBoard({ snapshot }: TeamProbabilityBoardProps) {
  const ordered = useMemo(
    () =>
      [...snapshot.team_probabilities].sort(
        (left, right) => right.champion_probability - left.champion_probability,
      ),
    [snapshot],
  );

  return (
    <section
      className="panel team-probability-board"
      aria-labelledby="race-heading"
    >
      <div className="section-heading">
        <div>
          <p className="eyebrow">CHAMPION RACE</p>
          <h2 id="race-heading">剩余球队夺冠概率</h2>
        </div>
        <span className="data-note">
          {ordered.length > 0
            ? `${ordered.length} 支球队仍在竞争`
            : "暂无存活球队"}
        </span>
      </div>

      {ordered.length === 0 ? (
        <div className="state-card">当前快照没有球队概率数据。</div>
      ) : (
        <ol className="race-board">
          {ordered.map((item, index) => (
            <li className="race-board__row" key={item.team}>
              <span className="race-board__rank">
                {String(index + 1).padStart(2, "0")}
              </span>
              <div className="race-board__bar" aria-hidden="true">
                <i
                  className={
                    index === 0
                      ? "race-board__fill race-board__fill--leader"
                      : "race-board__fill"
                  }
                  style={{
                    width: `${item.champion_probability * 100}%`,
                  }}
                />
              </div>
              <strong className="race-board__team">{item.team}</strong>
              <span className="race-board__final">
                进决赛 <ProbabilityValue value={item.final_probability} />
              </span>
              <ProbabilityValue
                className="race-board__champion"
                value={item.champion_probability}
              />
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
