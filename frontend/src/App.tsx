import { Suspense, lazy } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import CitizenShell from './citizen/CitizenShell'
import Home from './citizen/Home'
import Report from './citizen/Report'
import Ticket from './citizen/Ticket'
import Track from './citizen/Track'
import PublicMap from './citizen/PublicMap'
import { ToastProvider } from './components/ui/overlays'
import { Spinner } from './components/ui/primitives'
import { LanguageProvider } from './i18n'

// The officer dashboard is a separate bundle: a citizen on a slow connection
// should never download the admin code to file one complaint.
const AdminShell = lazy(() => import('./admin/AdminShell'))
const Login = lazy(() => import('./admin/Login'))
const Dashboard = lazy(() => import('./admin/Dashboard'))
const IssueDetail = lazy(() => import('./admin/IssueDetail'))
const Review = lazy(() => import('./admin/Review'))
const SlaDashboard = lazy(() => import('./admin/SlaDashboard'))
const Equity = lazy(() => import('./admin/Equity'))
const AiHealth = lazy(() => import('./admin/AiHealth'))
const AuditLog = lazy(() => import('./admin/AuditLog'))

function Loading() {
  return (
    <div className="min-h-[60vh] flex items-center justify-center text-brand-600">
      <Spinner className="h-7 w-7" />
    </div>
  )
}

export default function App() {
  return (
    <LanguageProvider>
      <ToastProvider>
        <BrowserRouter>
          <Suspense fallback={<Loading />}>
            <Routes>
              <Route element={<CitizenShell />}>
                <Route index element={<Home />} />
                <Route path="report" element={<Report />} />
                <Route path="ticket/:code" element={<Ticket />} />
                <Route path="track" element={<Track />} />
                <Route path="track/:code" element={<Track />} />
                <Route path="map" element={<PublicMap />} />
              </Route>

              <Route path="/admin/login" element={<Login />} />
              <Route path="/admin" element={<AdminShell />}>
                <Route index element={<Dashboard />} />
                <Route path="issues/:code" element={<IssueDetail />} />
                <Route path="review" element={<Review />} />
                <Route path="sla" element={<SlaDashboard />} />
                <Route path="equity" element={<Equity />} />
                <Route path="ai-health" element={<AiHealth />} />
                <Route path="audit" element={<AuditLog />} />
              </Route>

              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </Suspense>
        </BrowserRouter>
      </ToastProvider>
    </LanguageProvider>
  )
}
