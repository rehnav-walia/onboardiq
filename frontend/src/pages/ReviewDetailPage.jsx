import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { getApplication, getAuditLog, getDecision, getExtraction, getRisk, listDocuments } from '../api.js';
import AuditLogList from '../components/AuditLogList.jsx';
import ComparisonRow from '../components/ComparisonRow.jsx';
import DecisionForm from '../components/DecisionForm.jsx';
import DocumentPreview from '../components/DocumentPreview.jsx';
import RiskBadge from '../components/RiskBadge.jsx';

const FIELD_LABELS = {
  full_name: 'Full name',
  date_of_birth: 'Date of birth',
  id_number: 'ID number',
};

const DECIDABLE_STATUSES = new Set(['PENDING_REVIEW', 'INFO_REQUESTED']);

export default function ReviewDetailPage() {
  const { referenceId } = useParams();
  const navigate = useNavigate();

  const [application, setApplication] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [extractionData, setExtractionData] = useState(null);
  const [extractionError, setExtractionError] = useState('');
  const [auditLog, setAuditLog] = useState([]);
  const [riskData, setRiskData] = useState(null);
  const [decision, setDecision] = useState(null);
  const [loadError, setLoadError] = useState('');
  const [loading, setLoading] = useState(true);

  async function loadAll() {
    setLoading(true);
    setLoadError('');
    try {
      const [app, docs, log] = await Promise.all([
        getApplication(referenceId),
        listDocuments(referenceId),
        getAuditLog(referenceId),
      ]);
      setApplication(app);
      setDocuments(docs);
      setAuditLog(log);

      try {
        setExtractionData(await getExtraction(referenceId));
        setExtractionError('');
      } catch (err) {
        setExtractionData(null);
        setExtractionError(err.message || 'No extraction result is available yet for this application.');
      }

      try {
        setDecision(await getDecision(referenceId));
      } catch {
        setDecision(null);
      }

      try {
        setRiskData(await getRisk(referenceId));
      } catch {
        setRiskData(null);
      }
    } catch (err) {
      setLoadError(err.message || 'Could not load this application.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [referenceId]);

  if (loading) return <p>Loading…</p>;
  if (loadError) {
    return (
      <p className="form-error" role="alert">
        {loadError}
      </p>
    );
  }
  if (!application) return null;

  const latestDocument = documents[documents.length - 1];
  const submittedValues = {
    full_name: application.full_name,
    date_of_birth: application.date_of_birth,
    id_number: application.id_number,
  };

  const verificationByField = {};
  if (extractionData) {
    for (const result of extractionData.verification) {
      verificationByField[result.field_name] = result;
    }
  }

  const extractionSucceeded = extractionData?.extraction?.status === 'SUCCESS';
  const canDecide = !decision && DECIDABLE_STATUSES.has(application.status);

  return (
    <>
      <p>
        {/* navigate(-1) rather than a Link to a fixed "/reviewer" path — the
            latter would drop whatever filters/sort/page the reviewer had
            set (US-20 AC: filter state persists while navigating). */}
        <button type="button" className="link-button" onClick={() => navigate(-1)}>
          ← Back to queue
        </button>
      </p>
      <h1>Review {application.reference_id}</h1>
      <p className="review-status-line">
        Status: <strong>{application.status}</strong> · Flags: {application.flag_count} · Risk:{' '}
        <RiskBadge level={application.risk_level} />
      </p>

      {extractionError && (
        <p className="review-banner" role="status">
          ⚠ {extractionError} Please review the submitted data and document manually.
        </p>
      )}

      {extractionData?.extraction?.status === 'AI_UNAVAILABLE' && (
        <p className="review-banner" role="status">
          ⚠ AI extraction was unavailable for this document — please review the submitted data and document
          manually. ({extractionData.extraction.justification})
        </p>
      )}

      {extractionData?.extraction?.status === 'UNREADABLE' && (
        <p className="review-banner" role="status">
          ⚠ The AI reported this document as unreadable — please review manually. (
          {extractionData.extraction.justification})
        </p>
      )}

      <section className="review-columns">
        <div className="review-comparison">
          <h2>Submitted vs. Extracted</h2>
          {extractionSucceeded ? (
            <div className="comparison-grid">
              <div className="comparison-grid__header">
                <div>Field</div>
                <div>Submitted</div>
                <div>Extracted</div>
                <div>Result</div>
              </div>
              {Object.entries(FIELD_LABELS).map(([field, label]) => {
                const verification = verificationByField[field];
                return (
                  <ComparisonRow
                    key={field}
                    label={label}
                    submittedValue={submittedValues[field]}
                    extractedField={extractionData.extraction.fields[field]}
                    matchStatus={verification?.match_status}
                    matchJustification={verification?.justification}
                  />
                );
              })}
            </div>
          ) : (
            <div className="comparison-grid comparison-grid--manual">
              {Object.entries(FIELD_LABELS).map(([field, label]) => (
                <div className="comparison-row" key={field}>
                  <div className="comparison-row__label">{label}</div>
                  <div className="comparison-row__submitted">{submittedValues[field]}</div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="review-document">
          <h2>Uploaded document</h2>
          {latestDocument ? (
            <DocumentPreview referenceId={referenceId} document={latestDocument} />
          ) : (
            <p>No document uploaded.</p>
          )}
        </div>
      </section>

      <section className="review-risk">
        <h2>
          Risk assessment <RiskBadge level={riskData?.risk_level ?? application.risk_level} />
        </h2>
        <p className="review-risk__disclaimer">
          Advisory only — this never blocks or decides anything. You can approve, reject, or request more
          information regardless of the level shown here.
        </p>
        {riskData && riskData.factors.length > 0 ? (
          <ul className="review-risk__factors">
            {riskData.factors.map((factor) => (
              <li key={factor.code}>{factor.message}</li>
            ))}
          </ul>
        ) : riskData ? (
          <p>No contributing risk factors were identified.</p>
        ) : (
          <p>Risk has not been assessed yet for this application.</p>
        )}
      </section>

      <section className="review-decision">
        {decision ? (
          <div className="decision-recorded" role="status">
            <h2>Decision recorded</h2>
            <p>
              <strong>{decision.action}</strong> by {decision.reviewer_id} on{' '}
              {new Date(decision.decided_at).toLocaleString()}
            </p>
            {decision.reasoning && <p>{decision.reasoning}</p>}
          </div>
        ) : canDecide ? (
          <DecisionForm referenceId={referenceId} onDecided={loadAll} />
        ) : (
          <p>This application is not currently awaiting a decision.</p>
        )}
      </section>

      <section className="review-audit-log">
        <h2>Audit log</h2>
        <AuditLogList entries={auditLog} />
      </section>
    </>
  );
}
