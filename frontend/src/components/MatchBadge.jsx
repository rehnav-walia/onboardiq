// US-22 DoD: highlighting must be distinguishable without relying on
// colour alone — each status has its own symbol and text label, so colour
// (and colour-blindness, and greyscale printing) never carries the meaning
// on its own.
const CONFIG = {
  MATCH: { symbol: '✓', text: 'Match', className: 'match-badge--match' },
  PARTIAL_MATCH: { symbol: '~', text: 'Partial match', className: 'match-badge--partial' },
  MISMATCH: { symbol: '⚠', text: 'Mismatch', className: 'match-badge--mismatch' },
};

export default function MatchBadge({ status }) {
  const config = CONFIG[status] || { symbol: '?', text: status, className: '' };
  return (
    <span className={`match-badge ${config.className}`}>
      <span aria-hidden="true">{config.symbol}</span> {config.text}
    </span>
  );
}
