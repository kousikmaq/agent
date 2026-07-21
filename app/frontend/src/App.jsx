import React, { useState } from 'react'
import Sidebar from './components/Sidebar'
import DashboardPage from './pages/DashboardPage'
import CapacityPage from './pages/CapacityPage'
import PriorityPage from './pages/PriorityPage'
import AllocationPage from './pages/AllocationPage'
import SchedulePage from './pages/SchedulePage'
import DelayRiskPage from './pages/DelayRiskPage'
import DemandPage from './pages/DemandPage'
import ScenariosPage from './pages/ScenariosPage'
import AssistantWidget from './components/AssistantWidget'
import ErrorBoundary from './components/ErrorBoundary'

export default function App() {
  const [page, setPage] = useState('dashboard')
  const [week, setWeek] = useState(null)

  function goToWeek(w) { setWeek(w); setPage('capacity') }

  return (
    <div className="shell">
      <Sidebar page={page} setPage={setPage} />
      <main className="main">
        <ErrorBoundary key={page}>
          {page === 'dashboard' && <DashboardPage onSelectWeek={goToWeek} />}
          {page === 'capacity' && <CapacityPage week={week} setWeek={setWeek} />}
          {page === 'priority' && <PriorityPage week={week} setWeek={setWeek} />}
          {page === 'allocation' && <AllocationPage week={week} setWeek={setWeek} />}
          {page === 'schedule' && <SchedulePage week={week} setWeek={setWeek} />}
          {page === 'risk' && <DelayRiskPage week={week} setWeek={setWeek} />}
          {page === 'demand' && <DemandPage />}
          {page === 'scenarios' && <ScenariosPage week={week} setWeek={setWeek} />}
        </ErrorBoundary>
      </main>
      <AssistantWidget />
    </div>
  )
}
