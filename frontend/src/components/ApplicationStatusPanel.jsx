import { useEffect, useState } from 'react';

import { getApplication, getDecision, listDocuments } from '../api.js';
import DocumentPreview from './DocumentPreview.jsx';
import DocumentUpload from './DocumentUpload.jsx';

const STATUS_COPY = {
  SUBMITTED: 'Your application has been received.',
  PROCESSING: 'Your document is being processed.',
  PENDING_REVIEW: 'Your application is with a reviewer.',
  INFO_REQUESTED: 'A reviewer needs more information from you.',
  APPROVED: 'Your application has been approved.',
  REJECTED: 'Your application was not approved.',
};

// US-07/US-25: an upload or replacement is only possible while the backend
// would actually accept one — SUBMITTED (the very first document) or
// INFO_REQUESTED (a resubmission). Mirrors documents.py's
// _UPLOAD_ALLOWED_STATUSES (DRAFT is handled separately, before this panel
// is ever shown).
const UPLOAD_ALLOWED_STATUSES = new Set(['SUBMITTED', 'INFO_REQUESTED']);

export default function ApplicationStatusPanel({ application: initialApplication }) {
  const [application, setApplication] = useState(initialApplication);
  const [documents, setDocuments] = useState([]);
  const [latestDecision, setLatestDecision] = useState(null);
  const [loadError, setLoadError] = useState('');

  async function refresh(referenceId) {
    setLoadError('');
    try {
      const [app, docs] = await Promise.all([getApplication(referenceId), listDocuments(referenceId)]);
      setApplication(app);
      setDocuments(docs);
      try {
        setLatestDecision(await getDecision(referenceId));
      } catch {
        setLatestDecision(null);
      }
    } catch (err) {
      setLoadError(err.message || 'Could not load this application.');
    }
  }

  useEffect(() => {
    refresh(initialApplication.reference_id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialApplication.reference_id]);

  if (loadError) {
    return (
      <p className="form-error" role="alert">
        {loadError}
      </p>
    );
  }

  const currentDocument = documents.find((d) => !d.superseded);

  return (
    <section className="application-status-panel" role="status">
      <h2>Application {application.reference_id}</h2>
      <p>
        Status: <strong>{application.status}</strong> — {STATUS_COPY[application.status]}
      </p>

      {application.status === 'INFO_REQUESTED' && latestDecision && (
        <p className="review-banner" role="alert">
          ⚠ The reviewer asked for more information: <strong>{latestDecision.reasoning}</strong> Please upload a
          replacement document below.
        </p>
      )}

      {(application.status === 'APPROVED' || application.status === 'REJECTED') && latestDecision && (
        <p className={`decision-recorded decision-recorded--${application.status.toLowerCase()}`}>
          <strong>{latestDecision.action}</strong> by {latestDecision.reviewer_id} on{' '}
          {new Date(latestDecision.decided_at).toLocaleString()}
          {latestDecision.reasoning && <> — {latestDecision.reasoning}</>}
        </p>
      )}

      {UPLOAD_ALLOWED_STATUSES.has(application.status) ? (
        <DocumentUpload
          referenceId={application.reference_id}
          mode={documents.length > 0 ? 'replace' : 'upload'}
          onUploaded={() => refresh(application.reference_id)}
        />
      ) : (
        currentDocument && (
          <div className="document-upload">
            <h2>Your uploaded document</h2>
            <DocumentPreview referenceId={application.reference_id} document={currentDocument} />
          </div>
        )
      )}
    </section>
  );
}
