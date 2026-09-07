import AIValue from './AIValue.jsx';
import MatchBadge from './MatchBadge.jsx';

export default function ComparisonRow({ label, submittedValue, extractedField, matchStatus, matchJustification }) {
  const statusClass = matchStatus ? `comparison-row--${matchStatus.toLowerCase()}` : '';
  return (
    <div className={`comparison-row ${statusClass}`}>
      <div className="comparison-row__label">{label}</div>
      <div className="comparison-row__submitted">{submittedValue}</div>
      <div className="comparison-row__extracted">
        {extractedField ? (
          <AIValue
            value={extractedField.value}
            justification={extractedField.justification}
            confidence={extractedField.confidence}
            isLowConfidence={extractedField.is_low_confidence}
          />
        ) : (
          <span className="ai-value ai-value--withheld">Not extracted</span>
        )}
      </div>
      <div className="comparison-row__status">
        {matchStatus && <MatchBadge status={matchStatus} />}
        {matchJustification && <p className="comparison-row__match-justification">{matchJustification}</p>}
      </div>
    </div>
  );
}
