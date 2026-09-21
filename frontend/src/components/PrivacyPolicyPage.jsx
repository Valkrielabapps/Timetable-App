import LegalPage from './LegalPage'
import markdown from '../legal/privacy-policy.md?raw'

export default function PrivacyPolicyPage({ onBack }) {
  return <LegalPage title="the Privacy Policy" markdown={markdown} onBack={onBack} />
}
