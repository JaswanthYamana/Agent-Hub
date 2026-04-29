import { HashRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Suspense, lazy, useEffect } from 'react'
import { Layout } from './components/layout/Layout'
import useStore   from './store/useStore'

const Dashboard = lazy(() => import('./views/Dashboard'))
const Execute = lazy(() => import('./views/Execute'))
const Traces = lazy(() => import('./views/Traces'))
const Graph = lazy(() => import('./views/Graph'))
const Metrics = lazy(() => import('./views/Metrics'))
const Anomalies = lazy(() => import('./views/Anomalies'))
const Replay = lazy(() => import('./views/Replay'))
const RedTeam = lazy(() => import('./views/RedTeam'))
const Ingest = lazy(() => import('./views/Ingest'))
const Analytics = lazy(() => import('./views/Analytics'))
const Demo = lazy(() => import('./views/Demo'))
const Compare = lazy(() => import('./views/Compare'))
const Settings = lazy(() => import('./views/Settings'))

export default function App() {
  const checkHealth = useStore((s) => s.checkHealth)

  // Poll backend health every 20 s
  useEffect(() => {
    checkHealth()
    const id = setInterval(checkHealth, 20_000)
    return () => clearInterval(id)
  }, [checkHealth])

  return (
    <HashRouter>
      <Layout>
        <Suspense fallback={<div className="panel-loading">Loading view...</div>}>
          <Routes>
            <Route path="/"          element={<Navigate to="/dashboard" replace />} />
            <Route path="/demo"      element={<Demo />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/execute"   element={<Execute />} />
            <Route path="/traces"    element={<Traces />} />
            <Route path="/traces/:traceId" element={<Traces />} />
            <Route path="/graph"     element={<Graph />} />
            <Route path="/graph/:traceId"  element={<Graph />} />
            <Route path="/metrics"   element={<Metrics />} />
            <Route path="/anomalies" element={<Anomalies />} />
            <Route path="/replay"    element={<Replay />} />
            <Route path="/replay/:traceId" element={<Replay />} />
            <Route path="/redteam"    element={<RedTeam />} />
            <Route path="/ingest"     element={<Ingest />} />
            <Route path="/analytics"  element={<Analytics />} />
            <Route path="/compare"    element={<Compare />} />
            <Route path="/settings"   element={<Settings />} />
            <Route path="*"           element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </Suspense>
      </Layout>
    </HashRouter>
  )
}
