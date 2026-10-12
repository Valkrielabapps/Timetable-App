import LegalPage from './LegalPage'
import markdown from '../legal/refund-policy.md?raw'

export default function RefundPolicyPage({ onBack }) {
  return <LegalPage title="the Refund and Cancellation Policy" markdown={markdown} onBack={onBack} />
}
