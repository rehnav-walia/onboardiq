import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { fetchAuditExport, getApplication, getAuditLog, getDecisions, getExtraction, getRisk, listDocuments } from '../api.js';
import AuditLogList from '../components/AuditLogList.jsx';
import ComparisonRow from '../components/ComparisonRow.jsx';
import DecisionForm from '../components/DecisionForm.jsx';
import DocumentPreview from '../components/DocumentPreview.jsx';
import RiskBadge from '../components/RiskBadge.jsx';
import { clearReviewerSession } from '../reviewerAuth.js';

// US-28, made reviewer-only along with the rest of this page's data
// (addition on top of the PRD — see backend/app/auth.py): a plain <a href>
// can't carry the reviewer's session header, so the export is fetched as a
// Blob (with that header) and saved via a throwaway object URL instead.
function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

const FIELD_LABELS = {
  full_name: 'Full name',
  date_of_birth: 'Date of birth',
  id_number: 'ID number',
};

const DOCUMENT_TYPE_LABELS = {
  PASSPORT: 'Passport',
  NATIONAL_ID: 'National ID',
  DRIVING_LICENCE: 'Driving Licence',
};

export default function ReviewDetailPage() {
  const { referenceId } = useParams();
  const navigate = useNavigate();

  const [application, setApplication] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [extractionData, setExtractionData] = useState(null);
  const [extractionError, setExtractionError] = useState('');
  const [auditLog, setAuditLog] = useState([]);
  const [riskData, setRiskData] = useState(null);
  const [decisions, setDecisions] = useState([]);
  const [loadError, setLoadError] = useState('');
  const [loading, setLoading] = useState(true);
  const [exportError, setExportError] = useState('');

  async function loadAll() {
    setLoading(true);
    setLoadError('');
    try {
      const [app, docs, log, decisionHistory] = await Promise.all([
        getApplication(referenceId),
        listDocuments(referenceId),
        getAuditLog(referenceId),
        getDecisions(referenceId),
      ]);
      setApplication(app);
      setDocuments(docs);
      setAuditLog(log);
      setDecisions(decisionHistory);

      try {
        setExtractionData(await getExtraction(referenceId));
        setExtractionError('');
      } catch (err) {
        setExtractionData(null);
        setExtractionError(err.message || 'No extraction result is available yet for this application.');
      }

      try {
        setRiskData(await getRisk(referenceId));
      } catch {
        setRiskData(null);
      }
    } catch (err) {
      if (err.status === 401) {
        // Session expired or was cleared elsewhere (e.g. a backend
        // restart — see backend/app/auth.py's in-memory sessions).
        clearReviewerSession();
        navigate('/reviewer/login', { state: { from: `/reviewer/${referenceId}` }, replace: true });
        return;
      }
      setLoadError(err.message || 'Could not load this application.');
    } finally {
      setLoading(false);
    }
  }

  async function handleExport(format) {
    setExportError('');
    try {
      const { blob, filename } = await fetchAuditExport(referenceId, format);
      downloadBlob(blob, filename);
    } catch (err) {
      setExportError(err.message || 'Could not export the audit trail. Please try again.');
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

  const currentDocument = documents.find((d) => !d.superseded) ?? documents[documents.length - 1];
  const priorDocuments = documents.filter((d) => d !== currentDocument);
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
  // US-23/US-25: decidable purely on the CURRENT status — a prior decision
  // (e.g. an earlier REQUEST_INFO) never blocks a new one once resubmission
  // has returned the application to PENDING_REVIEW.
  const canDecide = application.status === 'PENDING_REVIEW';

  return (
    <>
      {/* "Back to queue" now lives in the persistent top nav (Layout.jsx)
          so it's visible immediately, even while this page is still
          loading or failed to load — see the loading/loadError early
          returns above, which this JSX never reaches in that case. */}
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
          {currentDocument ? (
            <>
              {currentDocument.declared_type && (
                <p className="review-document__declared-type">
                  Declared type: <strong>{DOCUMENT_TYPE_LABELS[currentDocument.declared_type]}</strong>
                  {currentDocument.detected_type && (
                    <> · AI-detected type: <strong>{currentDocument.detected_type}</strong></>
                  )}
                </p>
              )}
              {/* US-15 AC: rendered distinctly from the field-level
                  mismatches in the comparison grid above, not folded into
                  it. */}
              {currentDocument.type_mismatch === true && (
                <p className="review-banner review-banner--type-mismatch" role="alert">
                  ⚠ Declared/detected document type mismatch — this does not block a decision, but should be
                  reviewed.
                </p>
              )}
              <DocumentPreview referenceId={referenceId} document={currentDocument} />
              {priorDocuments.length > 0 && (
                <details className="review-document__history">
                  <summary>{priorDocuments.length} prior version(s) (US-07: retained for audit)</summary>
                  <ul>
                    {priorDocuments.map((doc) => (
                      <li key={doc.id}>
                        <p>
                          Version {doc.version}: {doc.original_filename} (superseded)
                        </p>
                        <DocumentPreview referenceId={referenceId} document={doc} />
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </>
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

      {/* US-25 DoD: prior review context retained and visible on the
          second review — shown regardless of whether a new decision can
          currently be made. */}
      {decisions.length > 0 && (
        <section className="review-decision-history">
          <h2>Decision history</h2>
          <ul>
            {decisions.map((d, index) => (
              <li key={index} className="decision-recorded" role="status">
                <strong>{d.action}</strong> by {d.reviewer_id} on {new Date(d.decided_at).toLocaleString()}
                {d.reasoning && <> — {d.reasoning}</>}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="review-decision">
        {canDecide ? (
          <DecisionForm referenceId={referenceId} onDecided={loadAll} />
        ) : (
          <p>This application is not currently awaiting a decision.</p>
        )}
      </section>

      <section className="review-audit-log">
        <h2>Audit log</h2>
        <div className="review-audit-log__export">
          <button type="button" className="link-button" onClick={() => handleExport('csv')}>
            Export CSV
          </button>
          <button type="button" className="link-button" onClick={() => handleExport('json')}>
            Export JSON
          </button>
        </div>
        {exportError && (
          <p className="form-error" role="alert">
            {exportError}
          </p>
        )}
        <AuditLogList entries={auditLog} />
      </section>
    </>
  );
}
