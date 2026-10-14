import React from 'react'

/**
 * Strips internal chunk ID citations such as [3ab80ad6529b_p1_c004]
 * from the response text for a clean, Claude-style user experience.
 */
export function stripChunkIdCitations(text) {
  if (!text || typeof text !== 'string') return text || ''

  return text
    // 1. Bracket containing chunk IDs (single or comma-separated)
    // e.g. [3ab80ad6529b_p1_c004] or [3ab80ad6529b_p1_c004, 9232c7e34eea_p2_c001]
    .replace(/\s*\[\s*(?:chunk\s*id\s*:\s*)?[a-zA-Z0-9_\-]+_p\d+_c\d+(?:\s*,\s*(?:chunk\s*id\s*:\s*)?[a-zA-Z0-9_\-]+_p\d+_c\d+)*\s*\]/gi, '')
    // 2. Any bracket with _p and _c chunk ID pattern
    .replace(/\s*\[\s*[^\]]*_p\d+_c\d+[^\]]*\s*\]/gi, '')
    // 3. Any bracket like [chunk_1] or [comp_101] or [chunk_id]
    .replace(/\s*\[\s*(?:chunk|comp|doc)_[a-zA-Z0-9_\-]+\s*\]/gi, '')
    .replace(/\s*\[\s*chunk_id\s*\]/gi, '')
    // 4. Remove bare unbracketed chunk IDs at end of string/sentence
    .replace(/\s*\b[a-f0-9]{8,}_p\d+_c\d+\b/gi, '')
    // 5. Clean up awkward spacing before punctuation caused by removing inline tags
    .replace(/\s+([.,;:!?])/g, '$1')
    .trim()
}

/**
 * Tokenizes and renders inline markdown formatting:
 * - Citations: [1], [2], [1, 2]
 * - Code: `code`
 * - Bold: **text**
 * - Italic: *text*
 */
export function renderInlineContent(text, onCitationClick) {
  if (!text) return null

  const cleanedText = stripChunkIdCitations(text)
  const tokens = cleanedText.split(/(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*|\[\d+(?:,\s*\d+)*\])/g)

  return tokens.map((token, i) => {
    if (!token) return null

    // Citation badge [1] or [1, 2]
    const citMatch = token.match(/^\[(\d+(?:,\s*\d+)*)\]$/)
    if (citMatch) {
      const numbers = citMatch[1].split(',').map(n => n.trim())
      return (
        <span key={i} className="claude-citation-badges-group">
          {numbers.map((num, idx) => (
            <button
              key={idx}
              type="button"
              className="claude-inline-citation"
              onClick={(e) => {
                e.stopPropagation()
                if (onCitationClick) onCitationClick(num)
              }}
              title={`View citation source [${num}]`}
            >
              {num}
            </button>
          ))}
        </span>
      )
    }

    // Inline code `...`
    if (token.startsWith('`') && token.endsWith('`') && token.length >= 2) {
      return (
        <code key={i} className="claude-inline-code">
          {token.slice(1, -1)}
        </code>
      )
    }

    // Bold **...**
    if (token.startsWith('**') && token.endsWith('**') && token.length >= 4) {
      return <strong key={i}>{token.slice(2, -2)}</strong>
    }

    // Italic *...*
    if (token.startsWith('*') && token.endsWith('*') && token.length >= 2) {
      return <em key={i}>{token.slice(1, -1)}</em>
    }

    return token
  })
}

/**
 * Parses markdown text into structured blocks (Paragraphs, Headings, Tables, Lists, Code blocks).
 */
export default function ClaudeMarkdown({ content, onCitationClick }) {
  if (!content) return null

  // Strip raw chunk ID citations before parsing
  const cleanedContent = stripChunkIdCitations(content)

  // Normalize newlines
  const text = cleanedContent.replace(/\r\n/g, '\n')
  const rawLines = text.split('\n')

  const blocks = []
  let i = 0

  while (i < rawLines.length) {
    const line = rawLines[i]
    const trimmed = line.trim()

    // 1. Skip blank lines
    if (!trimmed) {
      i++
      continue
    }

    // 2. Fenced Code Block: ```
    if (trimmed.startsWith('```')) {
      const lang = trimmed.slice(3).trim()
      const codeLines = []
      i++
      while (i < rawLines.length && !rawLines[i].trim().startsWith('```')) {
        codeLines.push(rawLines[i])
        i++
      }
      if (i < rawLines.length) i++ // consume closing ```
      blocks.push({
        type: 'code',
        lang,
        code: codeLines.join('\n')
      })
      continue
    }

    // 3. Markdown Table: Line contains | and next line has | --- |
    if (
      trimmed.startsWith('|') &&
      trimmed.endsWith('|') &&
      i + 1 < rawLines.length &&
      rawLines[i + 1].trim().startsWith('|') &&
      rawLines[i + 1].includes('---')
    ) {
      const headerLine = trimmed
      const alignLine = rawLines[i + 1].trim()
      i += 2

      const parseCells = (row) =>
        row
          .replace(/^\|/, '')
          .replace(/\|$/, '')
          .split('|')
          .map(c => c.trim())

      const headers = parseCells(headerLine)
      const rows = []

      while (
        i < rawLines.length &&
        rawLines[i].trim().startsWith('|') &&
        rawLines[i].trim().endsWith('|')
      ) {
        rows.push(parseCells(rawLines[i].trim()))
        i++
      }

      blocks.push({
        type: 'table',
        headers,
        rows
      })
      continue
    }

    // 4. Headings: #, ##, ###
    if (trimmed.startsWith('### ')) {
      blocks.push({ type: 'h3', text: trimmed.slice(4).trim() })
      i++
      continue
    }
    if (trimmed.startsWith('## ')) {
      blocks.push({ type: 'h2', text: trimmed.slice(3).trim() })
      i++
      continue
    }
    if (trimmed.startsWith('# ')) {
      blocks.push({ type: 'h1', text: trimmed.slice(2).trim() })
      i++
      continue
    }

    // 5. Blockquote: >
    if (trimmed.startsWith('>')) {
      const quoteLines = []
      while (i < rawLines.length && rawLines[i].trim().startsWith('>')) {
        quoteLines.push(rawLines[i].trim().replace(/^>\s?/, ''))
        i++
      }
      blocks.push({
        type: 'blockquote',
        text: quoteLines.join(' ')
      })
      continue
    }

    // 6. Unordered List: - , * , • 
    if (trimmed.match(/^[-*•]\s+/)) {
      const items = []
      while (i < rawLines.length && rawLines[i].trim().match(/^[-*•]\s+/)) {
        items.push(rawLines[i].trim().replace(/^[-*•]\s+/, ''))
        i++
      }
      blocks.push({
        type: 'ul',
        items
      })
      continue
    }

    // 7. Ordered List: 1. , 2. 
    if (trimmed.match(/^\d+\.\s+/)) {
      const items = []
      while (i < rawLines.length && rawLines[i].trim().match(/^\d+\.\s+/)) {
        items.push(rawLines[i].trim().replace(/^\d+\.\s+/, ''))
        i++
      }
      blocks.push({
        type: 'ol',
        items
      })
      continue
    }

    // 8. Normal Paragraph: Collect consecutive non-empty lines that aren't special
    const paraLines = []
    while (
      i < rawLines.length &&
      rawLines[i].trim() &&
      !rawLines[i].trim().startsWith('```') &&
      !rawLines[i].trim().startsWith('#') &&
      !rawLines[i].trim().startsWith('>') &&
      !rawLines[i].trim().match(/^[-*•]\s+/) &&
      !rawLines[i].trim().match(/^\d+\.\s+/) &&
      !(
        rawLines[i].trim().startsWith('|') &&
        i + 1 < rawLines.length &&
        rawLines[i + 1].includes('---')
      )
    ) {
      paraLines.push(rawLines[i].trim())
      i++
    }

    if (paraLines.length > 0) {
      blocks.push({
        type: 'paragraph',
        text: paraLines.join(' ')
      })
    }
  }

  return (
    <div className="claude-rendered-markdown">
      {blocks.map((block, idx) => {
        switch (block.type) {
          case 'h1':
            return (
              <h1 key={idx} className="claude-heading-1">
                {renderInlineContent(block.text, onCitationClick)}
              </h1>
            )
          case 'h2':
            return (
              <h2 key={idx} className="claude-heading-2">
                {renderInlineContent(block.text, onCitationClick)}
              </h2>
            )
          case 'h3':
            return (
              <h3 key={idx} className="claude-heading-3">
                {renderInlineContent(block.text, onCitationClick)}
              </h3>
            )
          case 'paragraph':
            return (
              <p key={idx} className="claude-prose-p">
                {renderInlineContent(block.text, onCitationClick)}
              </p>
            )
          case 'ul':
            return (
              <ul key={idx} className="claude-prose-ul">
                {block.items.map((item, itemIdx) => (
                  <li key={itemIdx} className="claude-prose-li">
                    {renderInlineContent(item, onCitationClick)}
                  </li>
                ))}
              </ul>
            )
          case 'ol':
            return (
              <ol key={idx} className="claude-prose-ol">
                {block.items.map((item, itemIdx) => (
                  <li key={itemIdx} className="claude-prose-li">
                    {renderInlineContent(item, onCitationClick)}
                  </li>
                ))}
              </ol>
            )
          case 'table':
            return (
              <div key={idx} className="claude-table-container">
                <table className="claude-markdown-table">
                  <thead>
                    <tr>
                      {block.headers.map((h, hIdx) => (
                        <th key={hIdx}>{renderInlineContent(h, onCitationClick)}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {block.rows.map((row, rIdx) => (
                      <tr key={rIdx}>
                        {row.map((cell, cIdx) => (
                          <td key={cIdx}>{renderInlineContent(cell, onCitationClick)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
          case 'code':
            return (
              <div key={idx} className="claude-code-block-wrapper">
                {block.lang && <div className="claude-code-lang">{block.lang}</div>}
                <pre className="claude-code-pre">
                  <code>{block.code}</code>
                </pre>
              </div>
            )
          case 'blockquote':
            return (
              <blockquote key={idx} className="claude-prose-quote">
                {renderInlineContent(block.text, onCitationClick)}
              </blockquote>
            )
          default:
            return null
        }
      })}
    </div>
  )
}
