import { EmptyState } from '../components/ui'
import { Link } from '../lib/router'

export function NotFoundPage({ path }: { path: string }) {
  return (
    <EmptyState title="Page not found">
      There is no page at “{path || '/'}”. <Link to="/">Return home</Link>.
    </EmptyState>
  )
}
