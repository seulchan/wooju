import { EmptyState } from '../components/ui'
import { Link } from '../lib/router'
import { tr, pick } from '../lib/i18n'

export function NotFoundPage({ path }: { path: string }) {
  return (
    <EmptyState title={tr('Page not found')}>
      {pick(`There is no page at “${path || '/'}”.`, `“${path || '/'}” 페이지가 없어요.`)}{' '}
      <Link to="/">{pick('Return home', '홈으로')}</Link>
    </EmptyState>
  )
}
