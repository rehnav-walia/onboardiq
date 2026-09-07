import { NavLink, Route, Routes } from 'react-router-dom';

import ApplicantFlow from './pages/ApplicantFlow.jsx';
import ReviewDetailPage from './pages/ReviewDetailPage.jsx';
import ReviewerQueuePage from './pages/ReviewerQueuePage.jsx';

export default function App() {
  return (
    <>
      <nav className="top-nav">
        <NavLink to="/" end>
          Apply
        </NavLink>
        <NavLink to="/reviewer">Reviewer Queue</NavLink>
      </nav>
      <main className="app-shell">
        <Routes>
          <Route path="/" element={<ApplicantFlow />} />
          <Route path="/reviewer" element={<ReviewerQueuePage />} />
          <Route path="/reviewer/:referenceId" element={<ReviewDetailPage />} />
        </Routes>
      </main>
    </>
  );
}
