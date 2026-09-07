import { useState } from 'react';

import ApplicationForm from '../components/ApplicationForm.jsx';
import ConfirmationPanel from '../components/ConfirmationPanel.jsx';
import DocumentUpload from '../components/DocumentUpload.jsx';

export default function ApplicantFlow() {
  const [application, setApplication] = useState(null);

  return (
    <>
      <h1>OnboardIQ — Account Application</h1>

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
