import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { getQueue } from '../api.js';

const PAGE_SIZE = 20;

export default function ReviewerQueuePage() {
  const [data, setData] = useState(null);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    setData(null);
    getQueue(PAGE_SIZE, offset)
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message || 'Could not load the reviewer queue.');
      });
    return () => {
      cancelled = true;
    };
  }, [offset]);

  return (
    <>
      <h1>Reviewer Queue</h1>

      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}

      {!data && !error && <p>Loading…</p>}

      {data && data.items.length === 0 && <p>No applications are currently awaiting review.</p>}

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
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((item) => (
                  <tr key={item.reference_id}>
                    <td>
                      <Link to={`/reviewer/${item.reference_id}`}>{item.reference_id}</Link>
                    </td>
                    <td>{item.full_name}</td>
                    <td>{new Date(item.submitted_at).toLocaleString()}</td>
                    <td>{item.flag_count}</td>
                    <td>{item.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="queue-pagination">
            <button type="button" onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))} disabled={offset === 0}>
              Previous
            </button>
            <span>
              {offset + 1}–{offset + data.items.length} of {data.total}
            </span>
            <button
              type="button"
              onClick={() => setOffset(offset + PAGE_SIZE)}
              disabled={offset + PAGE_SIZE >= data.total}
            >
              Next
            </button>
          </div>
        </>
      )}
    </>
  );
}
