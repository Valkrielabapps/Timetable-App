/**
 * Renders one of the plain-Markdown legal docs (src/legal/*.md, imported
 * as raw text via Vite's `?raw` suffix — see PrivacyPolicyPage.jsx /
 * TermsOfServicePage.jsx) as a styled page, instead of pulling in a full
 * markdown library (react-markdown/marked) for two static documents with
 * a deliberately narrow set of syntax (#, ##, bold, lists, a table, a
 * horizontal rule, an HTML comment at the top). `renderMarkdown` below is
 * a hand-rolled, line-by-line parser scoped to exactly that syntax — it
 * is NOT a general Markdown parser and will not handle nested lists, code
 * blocks, or links.
 *
 * Both source .md files (see docs/legal/ in the repo, which is where
 * these are actually authored/edited — this component just displays a
 * copy of them) still contain unfilled [BRACKETED] placeholders
 * (business address, support email, effective date, jurisdiction) — see
 * the draft notice this component renders above the content. Do not
 * remove that notice until those are filled in for real.
 */

// Splits "**bold**" segments out of a line of already-escaped-free plain
// text and returns an array of strings/<strong> elements — the only
// inline formatting either document uses.
function renderInline(text, keyPrefix) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g)
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={`${keyPrefix}-${i}`}>{part.slice(2, -2)}</strong>
    }
    return <span key={`${keyPrefix}-${i}`}>{part}</span>
  })
}

function renderMarkdown(source) {
  // Strip the leading HTML comment (the "PLACEHOLDER GUIDE" block) — it's
  // authoring guidance for whoever fills the doc in, not page content.
  const withoutComment = source.replace(/<!--[\s\S]*?-->/, '').trim()
  const lines = withoutComment.split('\n')

  const blocks = []
  let listItems = null
  let tableRows = null

  function flushList() {
    if (listItems) {
      blocks.push(
        <ul key={`list-${blocks.length}`} className="my-3 list-disc space-y-1.5 pl-5">
          {listItems.map((item, i) => (
            <li key={i}>{renderInline(item, `li-${blocks.length}-${i}`)}</li>
          ))}
        </ul>
      )
      listItems = null
    }
  }

  function flushTable() {
    if (tableRows && tableRows.length > 1) {
      const [header, , ...body] = tableRows // row 0 = header, row 1 = --- separator
      blocks.push(
        <table key={`table-${blocks.length}`} className="my-4 w-full border-collapse text-left text-sm">
          <thead>
            <tr className="border-b border-neutral-300">
              {header.map((cell, i) => (
                <th key={i} className="py-2 pr-4 font-semibold text-neutral-900">
                  {cell}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {body.map((row, ri) => (
              <tr key={ri} className="border-b border-neutral-100">
                {row.map((cell, ci) => (
                  <td key={ci} className="py-2 pr-4 text-neutral-600">
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )
    }
    tableRows = null
  }

  for (const rawLine of lines) {
    const line = rawLine.trim()

    if (line.startsWith('|')) {
      flushList()
      const cells = line.split('|').slice(1, -1).map((c) => c.trim())
      tableRows = tableRows || []
      tableRows.push(cells)
      continue
    }
    flushTable()

    if (line === '') continue

    if (line.startsWith('# ')) {
      flushList()
      blocks.push(
        <h1 key={blocks.length} className="font-serif text-4xl font-medium tracking-tight text-neutral-900">
          {line.slice(2)}
        </h1>
      )
    } else if (line.startsWith('## ')) {
      flushList()
      blocks.push(
        <h2 key={blocks.length} className="mt-10 font-serif text-2xl font-medium text-neutral-900">
          {line.slice(3)}
        </h2>
      )
    } else if (line.startsWith('### ')) {
      flushList()
      blocks.push(
        <h3 key={blocks.length} className="mt-6 text-lg font-semibold text-neutral-900">
          {line.slice(4)}
        </h3>
      )
    } else if (line.startsWith('- ')) {
      listItems = listItems || []
      listItems.push(line.slice(2))
    } else {
      flushList()
      blocks.push(
        <p key={blocks.length} className="mt-4 leading-relaxed text-neutral-600">
          {renderInline(line, `p-${blocks.length}`)}
        </p>
      )
    }
  }
  flushList()
  flushTable()

  return blocks
}

export default function LegalPage({ title, markdown, onBack }) {
  return (
    <div className="min-h-screen bg-white">
      <div className="border-b border-neutral-100">
        <div className="mx-auto flex max-w-3xl items-center justify-between px-6 py-5">
          <span className="text-[17px] font-bold tracking-tight text-neutral-900">Timetablz</span>
          <button onClick={onBack} className="text-sm font-medium text-neutral-500 hover:text-neutral-900">
            ← Back to home
          </button>
        </div>
      </div>

      <div className="mx-auto max-w-3xl px-6 py-14">
        {/* See this file's top docstring — both source documents still have
            unfilled [BRACKETED] placeholders (address, support email,
            effective date). This notice stays until those are filled in
            for real; removing it while placeholders remain would make the
            page look finished when it isn't. */}
        <div className="mb-10 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          Draft — {title} is still a working draft. Bracketed placeholders (business address, support
          email, effective date) haven't been filled in yet.
        </div>
        {renderMarkdown(markdown)}
      </div>
    </div>
  )
}
