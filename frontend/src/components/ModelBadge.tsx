import type { SnapshotProvenance } from "../types";

interface ModelBadgeProps {
  provenance: Pick<
    SnapshotProvenance,
    "snapshot_id" | "cutoff_at" | "model_version" | "data_sha256"
  >;
}

function beijingTime(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Shanghai",
    hour12: false,
  }).format(new Date(value));
}

export function ModelBadge({ provenance }: ModelBadgeProps) {
  return (
    <dl className="model-badge" aria-label="预测来源">
      <div>
        <dt>快照</dt>
        <dd>{provenance.snapshot_id}</dd>
      </div>
      <div>
        <dt>数据截止</dt>
        <dd>{beijingTime(provenance.cutoff_at)} CST</dd>
      </div>
      <div>
        <dt>模型</dt>
        <dd>{provenance.model_version}</dd>
      </div>
      <div>
        <dt>数据指纹</dt>
        <dd title={provenance.data_sha256}>
          {provenance.data_sha256.slice(0, 12)}…
        </dd>
      </div>
    </dl>
  );
}
