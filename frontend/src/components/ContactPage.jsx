import LegalPage from './LegalPage'
import markdown from '../legal/contact.md?raw'

export default function ContactPage({ onBack }) {
  return <LegalPage title="Contact" markdown={markdown} onBack={onBack} />
}
