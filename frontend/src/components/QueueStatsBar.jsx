// Read-only summary of where applications currently stand (addition on top
// of the PRD) — never gates or decides anything, purely a glanceable
// overview above the queue's own filters. `stats` is the backend's
// QueueStatsOut shape (getQueueStats in api.js); nothing here recomputes a
// count itself, it only renders what the server already aggregated.
// "Overdue" is deliberately NOT a sixth independent total — it's a count
// already included within Pending (and, in principle, Info Requested; see
// crud.get_queue_stats) above, not an addition on top of them. The label
// and tooltip both say so, so the five numbers never read as if they sum
// to more than the queue actually holds.
const ITEMS = [
  { key: 'pending_review', label: 'Pending' },
  { key: 'info_requested', label: 'Info Requested' },
  { key: 'approved', label: 'Approved' },
  { key: 'rejected', label: 'Rejected' },
  {
    key: 'overdue',
    label: 'Overdue (of Pending)',
    modifier: 'overdue',
    title: 'Counted within Pending above — not an additional total.',
  },
];

export default function QueueStatsBar({ stats }) {
  if (!stats) return null;

  return (
    <div className="queue-stats-bar" role="group" aria-label="Queue summary">
      {ITEMS.map(({ key, label, modifier, title }) => (
        <span key={key} className={`queue-stat${modifier ? ` queue-stat--${modifier}` : ''}`} title={title}>
          <span className="queue-stat__value">{stats[key]}</span>
          <span className="queue-stat__label">{label}</span>
        </span>
      ))}
    </div>
  );
}
