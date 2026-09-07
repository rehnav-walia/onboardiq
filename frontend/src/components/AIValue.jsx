// US-26 / CLAUDE.md non-negotiable #2: no AI output may render without a
// justification. This is enforced here structurally, not by convention —
// if a caller doesn't supply one (or the backend ever returns one blank),
// this component refuses to show the bare value at all.
export default function AIValue({ value, justification, confidence, isLowConfidence }) {
  const hasJustification = Boolean(justification && justification.trim());

  if (!hasJustification) {
    return (
      <span className="ai-value ai-value--withheld">
        ⚠ Value withheld — no justification available
      </span>
    );
  }

  return (
    <span className="ai-value">
      <span className="ai-value__text">{value === null || value === undefined || value === '' ? '—' : value}</span>
      {isLowConfidence && <span className="ai-value__badge">⚠ Low confidence ({Math.round(confidence * 100)}%)</span>}
      <span className="ai-value__justification">{justification}</span>
    </span>
  );
}
