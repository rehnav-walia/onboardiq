// Read-only summary of where applications currently stand (addition on top
// of the PRD) — never gates or decides anything, purely a glanceable
// overview above the queue's own filters. `stats` is the backend's
// QueueStatsOut shape (getQueueStats in api.js); nothing here recomputes a
// count itself, it only renders what the server already aggregated.
const ITEMS = [
  { key: 'pending_review', label: 'Pending' },
  { key: 'info_requested', label: 'Info Requested' },
  { key: 'approved', label: 'Approved' },
  { key: 'rejected', label: 'Rejected' },
  { key: 'overdue', label: 'Overdue', modifier: 'overdue' },
];

export default function QueueStatsBar({ stats }) {
  if (!stats) return null;

  return (
    <div className="queue-stats-bar" role="group" aria-label="Queue summary">
      {ITEMS.map(({ key, label, modifier }) => (
        <span key={key} className={`queue-stat${modifier ? ` queue-stat--${modifier}` : ''}`}>
          <span className="queue-stat__value">{stats[key]}</span>
          <span className="queue-stat__label">{label}</span>
        </span>
      ))}
    </div>
  );
}
