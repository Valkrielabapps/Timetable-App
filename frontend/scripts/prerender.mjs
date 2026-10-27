// After `vite build`: write each public page as its own HTML file, with the
// page's words already in it and its own title, description, canonical link
// and structured data - see src/prerender.jsx.
//
//   dist/index.html                  homepage
//   dist/pricing/index.html ...      one per page (served at /pricing)
//   dist/app.html                    the empty shell, for /admin
//   dist/sitemap.xml
//
// Vercel serves dist/pricing/index.html for /pricing. The browser still loads
// the same app bundle, which renders over the prerendered HTML.
import { mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const dist = join(root, 'dist')
const ssrDir = join(root, 'dist-ssr')

const { pages } = await import(pathToFileURL(join(ssrDir, 'prerender.js')).href)
const template = readFileSync(join(dist, 'index.html'), 'utf8')
writeFileSync(join(dist, 'app.html'), template)

const esc = (s) => s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

function setMeta(html, attr, key, value) {
  const re = new RegExp(`<meta\\s+${attr}="${key}"[\\s\\S]*?/>`)
  const tag = `<meta ${attr}="${key}" content="${esc(value)}" />`
  return re.test(html) ? html.replace(re, tag) : html.replace('</head>', `    ${tag}\n  </head>`)
}

function page(p) {
  let html = template
  html = html.replace(/<title>[\s\S]*?<\/title>/, `<title>${esc(p.title)}</title>`)
  html = setMeta(html, 'name', 'description', p.description)
  html = setMeta(html, 'property', 'og:title', p.title)
  html = setMeta(html, 'property', 'og:description', p.description)
  html = setMeta(html, 'property', 'og:url', p.canonical)
  html = setMeta(html, 'name', 'twitter:title', p.title)
  html = setMeta(html, 'name', 'twitter:description', p.description)
  const head = [
    `<link rel="canonical" href="${p.canonical}" />`,
    `<script type="application/ld+json">${JSON.stringify(p.jsonLd).replace(/</g, '\\u003c')}</script>`,
  ].join('\n    ')
  html = html.replace('</head>', `    ${head}\n  </head>`)
  return html.replace('<div id="root"></div>', `<div id="root"><div data-prerendered>${p.html}</div></div>`)
}

const today = new Date().toISOString().slice(0, 10)
const urls = []
for (const p of pages()) {
  const file = p.path === '/' ? join(dist, 'index.html') : join(dist, p.path.slice(1), 'index.html')
  mkdirSync(dirname(file), { recursive: true })
  writeFileSync(file, page(p))
  urls.push(p.canonical)
  console.log(`prerendered ${p.path.padEnd(16)} ${(p.html.length / 1024).toFixed(0)} kB`)
}

const priority = (u) => (u.endsWith('.com/') ? '1.0' : /privacy|terms|refunds/.test(u) ? '0.3' : '0.8')
writeFileSync(
  join(dist, 'sitemap.xml'),
  '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
    urls.map((u) => `  <url><loc>${u}</loc><lastmod>${today}</lastmod><priority>${priority(u)}</priority></url>`).join('\n') +
    '\n</urlset>\n',
)
rmSync(ssrDir, { recursive: true, force: true })
console.log(`sitemap.xml: ${urls.length} pages`)
