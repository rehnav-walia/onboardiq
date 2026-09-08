import { useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';

import { getQueue } from '../api.js';
import RiskBadge from '../components/RiskBadge.jsx';
import { clearReviewerSession } from '../reviewerAuth.js';

const PAGE_SIZE = 20;

// US-20 AC: filter state persists while navigating within the session.
// Living in the URL (via useSearchParams) means it survives navigating to
// a review screen and back — including the browser's own back button and
// a page refresh, which plain component state would not.
function readParams(searchParams) {
  return {
    status: searchParams.get('status') || '',
    risk_level: searchParams.get('risk_level') || '',
    sort_by: searchParams.get('sort_by') || 'submitted_at',
    sort_dir: searchParams.get('sort_dir') || 'asc',
    overdue_only: searchParams.get('overdue_only') === 'true',
    offset: Number(searchParams.get('offset') || 0),
  };
}

export default function ReviewerQueuePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const filters = readParams(searchParams);
  const navigate = useNavigate();

  const [data, setData] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setError('');
    getQueue({
      limit: PAGE_SIZE,
      offset: filters.offset,
      status: filters.status,
      risk_level: filters.risk_level,
      sort_by: filters.sort_by,
      sort_dir: filters.sort_dir,
      overdue_only: filters.overdue_only || undefined,
    })
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((err) => {
        if (cancelled) return;
        if (err.status === 401) {
          // Session expired or was logged out elsewhere (e.g. a server
          // restart, which drops all in-memory sessions — see
          // backend/app/auth.py) — back to login rather than showing a
          // raw error on a page the reviewer can no longer use.
          clearReviewerSession();
          navigate('/reviewer/login', { state: { from: '/reviewer' }, replace: true });
          return;
        }
        setError(err.message || 'Could not load the reviewer queue.');
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    filters.offset,
    filters.status,
    filters.risk_level,
    filters.sort_by,
    filters.sort_dir,
    filters.overdue_only,
  ]);

  function updateFilter(patch) {
    const next = { ...filters, ...patch, offset: 0 };
    const params = new URLSearchParams();
    if (next.status) params.set('status', next.status);
    if (next.risk_level) params.set('risk_level', next.risk_level);
    if (next.sort_by !== 'submitted_at') params.set('sort_by', next.sort_by);
    if (next.sort_dir !== 'asc') params.set('sort_dir', next.sort_dir);
    if (next.overdue_only) params.set('overdue_only', 'true');
    setSearchParams(params);
  }

  function goToOffset(newOffset) {
    const params = new URLSearchParams(searchParams);
    params.set('offset', String(newOffset));
    setSearchParams(params);
  }

  return (
    <>
      <h1>Reviewer Queue</h1>

      <div className="queue-filters">
        <label>
          Status
          <select value={filters.status} onChange={(e) => updateFilter({ status: e.target.value })}>
            <option value="">All</option>
            <option value="PENDING_REVIEW">Pending Review</option>
            <option value="INFO_REQUESTED">Info Requested</option>
          </select>
        </label>

        <label>
          Risk level
          <select value={filters.risk_level} onChange={(e) => updateFilter({ risk_level: e.target.value })}>
            <option value="">All</option>
            <option value="LOW">Low</option>
            <option value="MEDIUM">Medium</option>
            <option value="HIGH">High</option>
          </select>
        </label>

        <label>
          Sort by
          <select value={filters.sort_by} onChange={(e) => updateFilter({ sort_by: e.target.value })}>
            <option value="submitted_at">Submission time</option>
            <option value="risk_level">Risk level</option>
          </select>
        </label>

        <label>
          Direction
          <select value={filters.sort_dir} onChange={(e) => updateFilter({ sort_dir: e.target.value })}>
            <option value="asc">Ascending</option>
            <option value="desc">Descending</option>
          </select>
        </label>

        <label className="queue-filters__checkbox">
          <input
            type="checkbox"
            checked={filters.overdue_only}
            onChange={(e) => updateFilter({ overdue_only: e.target.checked })}
          />
          Overdue only
        </label>
      </div>

      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}

      {!data && !error && <p>Loading…</p>}

      {data && data.items.length === 0 && <p>No applications match the current filters.</p>}

      {data && data.items.length > 0 && (
        <>
          <div className="queue-table-wrapper">
            <table className="queue-table">
              <thead>
                <tr>
                  <th>Reference ID</th>
                  <th>Applicant</th>
                  <th>Submitted</th>
                  <th>Flags</th>
                  <th>Risk</th>
                  <th>Waiting</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((item) => (
                  <tr key={item.reference_id} className={item.is_overdue ? 'queue-row--overdue' : ''}>
                    <td>
                      <Link to={`/reviewer/${item.reference_id}`}>{item.reference_id}</Link>
                    </td>
                    <td>{item.full_name}</td>
                    <td>{new Date(item.submitted_at).toLocaleString()}</td>
                    <td>{item.flag_count}</td>
                    <td>
                      <RiskBadge level={item.risk_level} />
                    </td>
                    <td>
                      {item.hours_waiting === null ? (
                        '—'
                      ) : (
                        <>
                          {item.hours_waiting.toFixed(1)}h
                          {item.is_overdue && <span className="overdue-marker"> ⚠ Overdue</span>}
                        </>
                      )}
                    </td>
                    <td>{item.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="queue-pagination">
            <button
              type="button"
              onClick={() => goToOffset(Math.max(0, filters.offset - PAGE_SIZE))}
              disabled={filters.offset === 0}
            >
              Previous
            </button>
            <span>
              {filters.offset + 1}–{filters.offset + data.items.length} of {data.total}
            </span>
            <button
              type="button"
              onClick={() => goToOffset(filters.offset + PAGE_SIZE)}
              disabled={filters.offset + PAGE_SIZE >= data.total}
            >
              Next
            </button>
          </div>
        </>
      )}
    </>
  );
}
