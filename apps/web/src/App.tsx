import { useEffect } from 'react'

import { Layout } from './components/Layout'
import { SetupGate } from './components/SetupGate'
import { useRefreshController } from './lib/freshness'
import { routeKey, useRoute } from './lib/router'
import { HomePage } from './pages/HomePage'
import { KnowledgePage } from './pages/KnowledgePage'
import { InsightsPage } from './pages/InsightsPage'
import { SourcesPage } from './pages/SourcesPage'
import { SearchPage } from './pages/SearchPage'
import { RecordDetailPage } from './pages/RecordDetailPage'
import { NotFoundPage } from './pages/NotFoundPage'
import { ReviewPage } from './pages/ReviewPage'
import { HistoryPage } from './pages/HistoryPage'
import { SettingsPage } from './pages/SettingsPage'
import { AskPage } from './pages/AskPage'
import { NewNotePage } from './pages/NewNotePage'

export default function App() {
  const route = useRoute()
  useRefreshController()
  const key = routeKey(route)

  // Scroll to top on navigation (hash changes don't reset scroll for SPA pages).
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [key])

  let page
  switch (route.name) {
    case 'home':
      page = <HomePage />
      break
    case 'knowledge':
      page = <KnowledgePage />
      break
    case 'insights':
      page = <InsightsPage />
      break
    case 'sources':
      page = <SourcesPage />
      break
    case 'search':
      page = <SearchPage key={route.q} q={route.q} />
      break
    case 'review':
      page = <ReviewPage />
      break
    case 'history':
      page = <HistoryPage />
      break
    case 'settings':
      page = <SettingsPage />
      break
    case 'ask':
      page = <AskPage initial={route.q} />
      break
    case 'newNote':
      page = <NewNotePage kind={route.kind} ground={route.ground} />
      break
    case 'knowledgeDetail':
    case 'insightDetail':
    case 'sourceDetail':
    case 'recordDetail':
      page = <RecordDetailPage key={route.id} id={route.id} />
      break
    default:
      page = <NotFoundPage path={route.path} />
  }

  return (
    <SetupGate>
      <Layout route={route}>
        <div key={key}>{page}</div>
      </Layout>
    </SetupGate>
  )
}
