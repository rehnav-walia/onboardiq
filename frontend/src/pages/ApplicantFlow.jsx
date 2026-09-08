import { useState } from 'react';

import ApplicationForm from '../components/ApplicationForm.jsx';
import ApplicationStatusPanel from '../components/ApplicationStatusPanel.jsx';
import ConfirmationPanel from '../components/ConfirmationPanel.jsx';
import PolicyAssistantChat from '../components/PolicyAssistantChat.jsx';
import ResumeLookup from '../components/ResumeLookup.jsx';

export default function ApplicantFlow() {
  const [application, setApplication] = useState(null);
  // US-03: a resumed DRAFT is edited in the same ApplicationForm as a new
  // application — everything else (SUBMITTED and later) goes to the status
  // panel instead, which is also how US-25's resubmission loop is reached.
  const [draft, setDraft] = useState(null);
  const [justSubmitted, setJustSubmitted] = useState(false);

  function handleFound(found) {
    if (found.status === 'DRAFT') {
      setDraft(found);
    } else {
      setApplication(found);
    }
  }

  function handleSubmitted(submitted) {
    setDraft(null);
    setJustSubmitted(true);
    setApplication(submitted);
  }

  return (
    <>
      <h1>OnboardIQ — Account Application</h1>

      {/* US-30 AC: chat interface available during the application flow —
          present throughout, not just after submission. */}
      <PolicyAssistantChat />

      {!application && !draft && (
        <>
          <ResumeLookup onFound={handleFound} />
          <ApplicationForm onSubmitted={handleSubmitted} />
        </>
      )}

      {draft && <ApplicationForm initialDraft={draft} onSubmitted={handleSubmitted} />}

      {application && (
        <>
          {justSubmitted && <ConfirmationPanel application={application} />}
          <ApplicationStatusPanel application={application} />
        </>
      )}
    </>
  );
}
