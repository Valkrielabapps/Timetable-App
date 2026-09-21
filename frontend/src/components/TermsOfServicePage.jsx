import LegalPage from './LegalPage'
import markdown from '../legal/terms-of-service.md?raw'

export default function TermsOfServicePage({ onBack }) {
  return <LegalPage title="the Terms of Service" markdown={markdown} onBack={onBack} />
}
