import { probabilityPercent } from "../api";

interface ProbabilityValueProps {
  value: number;
  className?: string;
}

export function ProbabilityValue({ value, className }: ProbabilityValueProps) {
  try {
    return <span className={className}>{probabilityPercent(value)}</span>;
  } catch {
    return (
      <span className="invalid-probability" role="status">
        概率数据非法
      </span>
    );
  }
}
