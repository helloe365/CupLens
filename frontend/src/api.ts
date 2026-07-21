import type {
  ChatResponse,
  Snapshot,
  SnapshotComparison,
  SnapshotIndexEntry,
} from "./types";

export function probabilityPercent(value: number): string {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0 || value > 1) {
    throw new Error("invalid probability");
  }

  return `${(value * 100).toFixed(1)}%`;
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch {
    throw new Error("暂时无法连接预测服务，请稍后重试");
  }

  if (!response.ok) {
    throw new Error(`暂时无法读取预测数据（HTTP ${response.status}）`);
  }

  try {
    return (await response.json()) as T;
  } catch {
    throw new Error("预测服务返回了无法识别的数据");
  }
}

export function getLatestSnapshot(): Promise<Snapshot> {
  return requestJson<Snapshot>("/api/snapshots/latest");
}

export function getSnapshots(): Promise<SnapshotIndexEntry[]> {
  return requestJson<SnapshotIndexEntry[]>("/api/snapshots");
}

export function getSnapshot(snapshotId: string): Promise<Snapshot> {
  return requestJson<Snapshot>(
    `/api/snapshots/${encodeURIComponent(snapshotId)}`,
  );
}

export function compareSnapshots(
  baseSnapshotId: string,
  targetSnapshotId: string,
): Promise<SnapshotComparison> {
  const query = new URLSearchParams({
    base: baseSnapshotId,
    target: targetSnapshotId,
  });
  return requestJson<SnapshotComparison>(`/api/snapshots/compare?${query}`);
}

export function askAgent(question: string): Promise<ChatResponse> {
  return requestJson<ChatResponse>("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
}
