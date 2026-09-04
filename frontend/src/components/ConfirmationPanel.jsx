export default function ConfirmationPanel({ application }) {
  return (
    <section className="confirmation-panel" role="status">
      <h2>Application submitted</h2>
      <p>
        Your reference ID is <strong>{application.reference_id}</strong>. Save this — you will
        need it to check on your application later.
      </p>
      <p>Status: {application.status}</p>
    </section>
  );
}
