import { Route, Routes } from 'react-router-dom';

import Layout from './components/Layout.jsx';
import RequireReviewerAuth from './components/RequireReviewerAuth.jsx';
import ApplicantFlow from './pages/ApplicantFlow.jsx';
import ReviewDetailPage from './pages/ReviewDetailPage.jsx';
import ReviewerLoginPage from './pages/ReviewerLoginPage.jsx';
import ReviewerQueuePage from './pages/ReviewerQueuePage.jsx';

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<ApplicantFlow />} />
        <Route path="/reviewer/login" element={<ReviewerLoginPage />} />
        <Route
          path="/reviewer"
          element={
            <RequireReviewerAuth>
              <ReviewerQueuePage />
            </RequireReviewerAuth>
          }
        />
        <Route
          path="/reviewer/:referenceId"
          element={
            <RequireReviewerAuth>
              <ReviewDetailPage />
            </RequireReviewerAuth>
          }
        />
      </Route>
    </Routes>
  );
}
