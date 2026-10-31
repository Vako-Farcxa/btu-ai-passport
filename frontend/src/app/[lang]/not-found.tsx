import { StatusPage } from '@/components/status-page'

export const metadata = { title: 'Page not found' }

export default function NotFound() {
  return <StatusPage kind="not_found" />
}
