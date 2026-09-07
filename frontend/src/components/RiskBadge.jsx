// US-16: risk is advisory only — this badge never disables or gates
// anything, it's purely informational. Distinguishable without relying on
// colour alone, same principle as MatchBadge.
const CONFIG = {
  LOW: { symbol: '●', text: 'Low', className: 'risk-badge--low' },
  MEDIUM: { symbol: '▲', text: 'Medium', className: 'risk-badge--medium' },
  HIGH: { symbol: '■', text: 'High', className: 'risk-badge--high' },
};

export default function RiskBadge({ level }) {
  if (!level) {
    return <span className="risk-badge risk-badge--unscored">Not yet assessed</span>;
  }
  const config = CONFIG[level] || { symbol: '?', text: level, className: '' };
  return (
    <span className={`risk-badge ${config.className}`}>
      <span aria-hidden="true">{config.symbol}</span> {config.text}
    </span>
  );
}
