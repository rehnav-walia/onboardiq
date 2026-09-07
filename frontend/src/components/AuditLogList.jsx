export default function AuditLogList({ entries }) {
  if (!entries || entries.length === 0) {
    return <p>No audit entries yet.</p>;
  }

  return (
    <ol className="audit-log">
      {entries.map((entry, index) => (
        <li key={index} className="audit-log__entry">
          <div className="audit-log__meta">
            <span className="audit-log__timestamp">{new Date(entry.timestamp).toLocaleString()}</span>
            <span className="audit-log__actor">{entry.actor}</span>
            <span className="audit-log__action">{entry.action}</span>
          </div>
          <p className="audit-log__details">{entry.details}</p>
        </li>
      ))}
    </ol>
  );
}
