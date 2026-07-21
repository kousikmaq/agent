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
  // Jump to any page, optionally pre-selecting a week (used by "create plan from scenario").
  function navigate(target, w) { if (w) setWeek(w); setPage(target) }

  return (
    <div className="shell">
      <Sidebar page={page} setPage={setPage} />
      <main className="main">
        <ErrorBoundary key={page}>
          {page === 'dashboard' && <DashboardPage onSelectWeek={goToWeek} navigate={navigate} />}
          {page === 'capacity' && <CapacityPage week={week} setWeek={setWeek} navigate={navigate} />}
          {page === 'priority' && <PriorityPage week={week} setWeek={setWeek} navigate={navigate} />}
          {page === 'allocation' && <AllocationPage week={week} setWeek={setWeek} navigate={navigate} />}
          {page === 'schedule' && <SchedulePage week={week} setWeek={setWeek} navigate={navigate} />}
          {page === 'risk' && <DelayRiskPage week={week} setWeek={setWeek} navigate={navigate} />}
          {page === 'demand' && <DemandPage navigate={navigate} />}
          {page === 'scenarios' && <ScenariosPage week={week} setWeek={setWeek} navigate={navigate} />}
        </ErrorBoundary>
      </main>
      <AssistantWidget />
    </div>
  )
}
