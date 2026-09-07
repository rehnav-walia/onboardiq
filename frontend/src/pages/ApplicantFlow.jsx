import { useState } from 'react';

import ApplicationForm from '../components/ApplicationForm.jsx';
import ConfirmationPanel from '../components/ConfirmationPanel.jsx';
import DocumentUpload from '../components/DocumentUpload.jsx';
import PolicyAssistantChat from '../components/PolicyAssistantChat.jsx';

export default function ApplicantFlow() {
  const [application, setApplication] = useState(null);

  return (
    <>
      <h1>OnboardIQ — Account Application</h1>

      {/* US-30 AC: chat interface available during the application flow —
          present throughout, not just after submission. */}
      <PolicyAssistantChat />

      {!application && <ApplicationForm onSubmitted={setApplication} />}

      {application && (
        <>
          <ConfirmationPanel application={application} />
          <DocumentUpload referenceId={application.reference_id} />
        </>
      )}
    </>
  );
}
