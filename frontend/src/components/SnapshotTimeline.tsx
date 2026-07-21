import type { SnapshotIndexEntry } from "../types";

interface SnapshotTimelineProps {
  entries: SnapshotIndexEntry[];
  selectedId: string;
  onSelect: (snapshotId: string) => void;
}

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

function modelShort(version: string): string {
  if (version.length <= 18) return version;
  return `${version.slice(0, 16)}…`;
}

export function SnapshotTimeline({
  entries,
  selectedId,
  onSelect,
}: SnapshotTimelineProps) {
  if (entries.length === 0) {
    return <div className="state-card">快照索引为空。</div>;
  }

  return (
    <section
      className="panel snapshot-timeline"
      aria-labelledby="timeline-heading"
    >
      <div className="section-heading">
        <div>
          <p className="eyebrow">SNAPSHOT TIMELINE</p>
          <h2 id="timeline-heading">快照时间轴</h2>
        </div>
        <span className="data-note">{entries.length} 个不可覆盖快照</span>
      </div>

      <div
        className="timeline-scroll"
        role="region"
        aria-label="快照时间轴"
        tabIndex={0}
      >
        <ol className="timeline-track">
          {entries.map((entry, index) => {
            const isSelected = entry.snapshot_id === selectedId;
            const isFirst = index === 0;
            const isLast = index === entries.length - 1;
            return (
              <li
                className={`timeline-node${isSelected ? " timeline-node--active" : ""}`}
                key={entry.snapshot_id}
              >
                <button
                  type="button"
                  aria-current={isSelected ? "location" : undefined}
                  aria-label={`${isFirst ? "最早" : isLast ? "最新" : `第 ${index + 1} 个`}快照：${entry.snapshot_id}`}
                  onClick={() => onSelect(entry.snapshot_id)}
                >
                  <i aria-hidden="true" />
                  <span className="timeline-node__time">
                    {beijingDate(entry.generated_at)}
                  </span>
                  <span className="timeline-node__id">{entry.snapshot_id}</span>
                  <span
                    className="timeline-node__model"
                    title={entry.model_version}
                  >
                    {modelShort(entry.model_version)}
                  </span>
                </button>
              </li>
            );
          })}
        </ol>
      </div>
      <p className="timeline-hint timeline-hint--callout">
        <i aria-hidden="true" />
        点击任一节点切换查看对应历史快照。
      </p>
    </section>
  );
}
