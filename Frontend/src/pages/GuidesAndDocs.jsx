import React, { useState, useMemo } from 'react'
import {
  BookOpen,
  HelpCircle,
  FileText,
  CheckCircle2,
  Sparkles,
  Search,
  ShieldCheck,
  Copy,
  Check,
  ArrowRight,
  Split,
  Filter,
  Zap,
  Lock,
  MessageSquare,
  UploadCloud,
  Layers,
  ChevronDown,
  ChevronUp,
  Table,
  Eye,
  FolderOpen
} from 'lucide-react'

export default function GuidesAndDocs({ onNavigateTab }) {
  const [activeCategory, setActiveCategory] = useState('overview')
  const [searchQuery, setSearchQuery] = useState('')
  const [copiedKey, setCopiedKey] = useState(null)
  const [expandedFaq, setExpandedFaq] = useState(null)
  const [expandedPrompt, setExpandedPrompt] = useState(null)

  const handleCopy = (key, text) => {
    navigator.clipboard.writeText(text)
    setCopiedKey(key)
    setTimeout(() => {
      setCopiedKey(null)
    }, 2000)
  }

  const toggleFaq = (idx) => {
    setExpandedFaq(expandedFaq === idx ? null : idx)
  }

  const togglePrompt = (idx) => {
    setExpandedPrompt(expandedPrompt === idx ? null : idx)
  }

  const CATEGORIES = [
    { id: 'overview', name: 'Product Overview', icon: BookOpen },
    { id: 'how-to-use', name: 'Getting Started Guide', icon: Zap },
    { id: 'prompting', name: 'Question & Prompt Guide', icon: MessageSquare },
    { id: 'document-mgmt', name: 'Document Management', icon: FolderOpen },
    { id: 'citations', name: 'Citations & Verification', icon: ShieldCheck },
    { id: 'security-faq', name: 'Privacy & FAQs', icon: Lock }
  ]

  const FAQS = [
    {
      q: 'How does MARVO AI find answers in my company documents?',
      a: 'When you ask a question, MARVO AI searches across your uploaded workplace documents, finds the exact paragraphs, policies, and tables that answer your question, and delivers a clear, direct answer with verified citations showing the source document name and page number.'
    },
    {
      q: 'What types of documents can I upload to MARVO AI?',
      a: 'MARVO AI supports PDF documents up to 50MB and 150 pages each, including HR employee handbooks, IT security standards, standard operating procedures (SOPs), technical architecture specifications, vendor contracts, and policy manuals.'
    },
    {
      q: 'Can MARVO AI compare two different policies or documents?',
      a: 'Yes! MARVO AI excels at comparison questions (e.g. comparing Health Plan A vs Health Plan B or Remote Work Policy vs Travel Guidelines). When it detects a comparison inquiry, it automatically structures key attributes side-by-side in a comparative table.'
    },
    {
      q: 'How can I verify that an answer is accurate and not hallucinated?',
      a: 'Every answer produced by MARVO AI includes interactive citation badges (e.g., [1], [2]) indicating the exact document title and page number. Clicking on any citation highlights the verbatim source snippet so you can immediately audit the underlying policy.'
    },
    {
      q: 'Are my uploaded documents private and secure?',
      a: 'Yes. Documents you upload are strictly isolated to your authenticated account. Other users cannot see or search your files. Furthermore, enterprise document content is never used to train public AI models.'
    },
    {
      q: 'How do I search within a single document instead of all files?',
      a: 'In the Ask AI search interface, click the "Document Scope" dropdown next to the input box. You can select an individual document to restrict searches strictly to that file, or select "All Documents" to search across your entire indexed library.'
    }
  ]

  const PROMPT_QUESTIONS = [
    {
      id: 'comparison',
      category: 'Comparison Questions',
      tagClass: 'tag-comparison',
      q: 'How do I ask side-by-side comparison questions between policies or plans?',
      summary: 'Use keywords like "Compare", "Difference between", or "Versus" when evaluating two or more tiers, plans, or guidelines across your documents.',
      example: 'Compare the deductible, out-of-pocket maximum, and copay between Health Plan Silver and Health Plan Gold.',
      systemAction: 'MARVO AI extracts facts for both options, lines up matching criteria, and automatically presents a structured comparative table with citations.'
    },
    {
      id: 'multidoc',
      category: 'Multi-Document',
      tagClass: 'tag-multidoc',
      q: 'How do I ask questions spanning multiple different documents at once?',
      summary: 'Formulate queries that cross-reference rules across disparate manuals (e.g., IT Security standard vs. Employee Travel Handbook).',
      example: 'According to our IT Security Policy and Employee Handbook, what are the VPN requirements when working remotely, and how do I expense home internet?',
      systemAction: 'MARVO AI searches across your library, balances findings from each referenced file, and synthesizes a unified answer so neither document is overlooked.'
    },
    {
      id: 'procedural',
      category: 'Procedures & Steps',
      tagClass: 'tag-multihop',
      q: 'How do I query step-by-step procedures, workflows, and incident reporting?',
      summary: 'Request sequential action steps, approval hierarchies, or escalation paths for workplace workflows.',
      example: 'What are the mandatory steps to follow when reporting a lost company laptop, and who must be notified first?',
      systemAction: 'MARVO AI extracts the chronological procedure and formats the response as clear, numbered, actionable steps with cited page locations.'
    },
    {
      id: 'factual',
      category: 'Factual Lookup',
      tagClass: 'tag-multisection',
      q: 'How do I look up specific numbers, per-diems, and policy allowances?',
      summary: 'Ask targeted questions for concrete figures, reimbursement limits, deadlines, or qualification criteria.',
      example: 'What is the maximum daily meal allowance during international business travel, and do I need itemized receipts?',
      systemAction: 'MARVO AI pinpoints the exact policy clause, quotes the figure in context, and provides verifiable page references.'
    },
    {
      id: 'scope',
      category: 'Scope Filtering',
      tagClass: 'tag-comparison',
      q: 'How do I use the Document Scope selector to search a single file?',
      summary: 'Use the Document Scope dropdown in the Ask AI search bar to isolate your inquiry to an individual PDF.',
      example: 'Select "Orbit_Security_Policy.pdf" in the dropdown before asking: "What encryption standard is required for company thumb drives?"',
      systemAction: 'MARVO AI restricts its retrieval strictly to that single document, ensuring maximum speed and zero irrelevant noise from other files.'
    },
    {
      id: 'followups',
      category: 'Conversational',
      tagClass: 'tag-multidoc',
      q: 'How do I ask conversational follow-up questions in the same chat thread?',
      summary: 'Stay in the same chat thread to ask clarifying questions without having to re-explain previous context.',
      example: 'After an answer on PTO: "Does that same carryover policy apply to part-time contractors?" or "Can you summarize that in 3 bullet points?"',
      systemAction: 'MARVO AI tracks the dialogue history in your active chat, maintaining context while looking up any additional clauses needed.'
    }
  ]

  // Filter FAQs if user types in search bar
  const filteredFaqs = useMemo(() => {
    if (!searchQuery.trim()) return FAQS
    const q = searchQuery.toLowerCase()
    return FAQS.filter(
      (item) => item.q.toLowerCase().includes(q) || item.a.toLowerCase().includes(q)
    )
  }, [searchQuery])

  // Filter Prompt Questions if user types in search bar
  const filteredPrompts = useMemo(() => {
    if (!searchQuery.trim()) return PROMPT_QUESTIONS
    const q = searchQuery.toLowerCase()
    return PROMPT_QUESTIONS.filter(
      (item) =>
        item.q.toLowerCase().includes(q) ||
        item.summary.toLowerCase().includes(q) ||
        item.example.toLowerCase().includes(q) ||
        item.category.toLowerCase().includes(q)
    )
  }, [searchQuery])

  return (
    <div className="docs-page-container">
      {/* Top Banner / Header */}
      <header className="docs-header">
        <div className="docs-header-left">
          <h1 className="docs-title">MARVO AI Guide </h1>
          <p className="docs-subtitle">
            Learn what MARVO AI does, how to search company policies, upload and manage documentation, and verify grounded answers.
          </p>
        </div>

        {/* Search within Docs */}
        <div className="docs-search-bar">
          <Search size={16} className="docs-search-icon" />
          <input
            type="text"
            className="docs-search-input"
            placeholder="Search guides, tips, or FAQs..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          {searchQuery && (
            <button
              className="docs-search-clear"
              onClick={() => setSearchQuery('')}
              title="Clear search"
            >
              ✕
            </button>
          )}
        </div>
      </header>

      {/* Navigation Pills */}
      <nav className="docs-category-nav" aria-label="Documentation Categories">
        {CATEGORIES.map((cat) => {
          const Icon = cat.icon
          const isActive = activeCategory === cat.id
          return (
            <button
              key={cat.id}
              className={`docs-category-pill ${isActive ? 'active' : ''}`}
              onClick={() => setActiveCategory(cat.id)}
            >
              <Icon size={15} />
              <span>{cat.name}</span>
            </button>
          )
        })}
      </nav>

      {/* Main Content Body */}
      <main className="docs-content-wrapper">
        {/* ==================== 1. PRODUCT OVERVIEW ==================== */}
        {activeCategory === 'overview' && (
          <section className="docs-section">
            <div className="docs-hero-card">
              <div className="docs-hero-content">
                <span className="docs-pill-accent">Enterprise Knowledge Assistant</span>
                <h2 className="docs-hero-title">Instant, Grounded Answers from Your Company Knowledge</h2>
                <p className="docs-hero-desc">
                  MARVO AI eliminates hours spent manually skimming through lengthy PDF manuals, HR policies, and technical specifications. Simply ask a question in natural language, and MARVO AI analyzes your workplace documentation to deliver a direct, comprehensive answer with verifiable citations.
                </p>

                <div className="docs-hero-actions">
                  {onNavigateTab && (
                    <button
                      className="docs-primary-btn"
                      onClick={() => onNavigateTab('Ask AI')}
                    >
                      <Sparkles size={15} />
                      <span>Start Searching in Ask AI</span>
                    </button>
                  )}
                  <button
                    className="docs-secondary-btn"
                    onClick={() => setActiveCategory('how-to-use')}
                  >
                    <span>Read Getting Started Guide</span>
                    <ArrowRight size={14} />
                  </button>
                </div>
              </div>
            </div>

            {/* What the system does: 4 Key Superpowers */}
            <h3 className="docs-subheading">
              <span>What MARVO AI Does For You</span>
            </h3>

            <div className="docs-grid-2">
              <div className="docs-feature-item">
                <div className="feature-icon-box">
                  <ShieldCheck size={18} />
                </div>
                <div>
                  <h4 className="feature-item-title">100% Grounded in Your Documents</h4>
                  <p className="feature-item-desc">
                    Unlike generic public chatbots, MARVO AI only answers based on the official documentation you provide. If an answer cannot be found in your uploaded files, it clearly tells you rather than inventing information.
                  </p>
                </div>
              </div>

              <div className="docs-feature-item">
                <div className="feature-icon-box">
                  <Table size={18} />
                </div>
                <div>
                  <h4 className="feature-item-title">Side-by-Side Policy Comparison</h4>
                  <p className="feature-item-desc">
                    Comparing benefits, software tiers, or security requirements across multiple guidelines? MARVO AI automatically structures key criteria into side-by-side comparison tables for easy decision-making.
                  </p>
                </div>
              </div>

              <div className="docs-feature-item">
                <div className="feature-icon-box">
                  <Eye size={18} />
                </div>
                <div>
                  <h4 className="feature-item-title">Interactive Source Citations</h4>
                  <p className="feature-item-desc">
                    Every key statement includes clickable source badges linking directly to the specific document title and page number, enabling instant auditability and verification.
                  </p>
                </div>
              </div>

              <div className="docs-feature-item">
                <div className="feature-icon-box">
                  <Split size={18} />
                </div>
                <div>
                  <h4 className="feature-item-title">Multi-Document Cross-Referencing</h4>
                  <p className="feature-item-desc">
                    Answers complex multi-part questions that require synthesizing facts scattered across different manuals (e.g. IT Security Policy + Remote Work Expense Guide).
                  </p>
                </div>
              </div>
            </div>

            {/* Who is it for */}
            <h3 className="docs-subheading" style={{ marginTop: '32px' }}>
              <Layers size={18} className="text-accent" />
              <span>Common Workplace Use Cases</span>
            </h3>

            <div className="docs-grid-3">
              <div className="docs-card">
                <h4 className="docs-card-title">👥 HR & People Operations</h4>
                <p className="docs-card-text">
                  Instant answers on leave policies, medical insurance tiers, remote work stipends, parental leave, and onboarding requirements.
                </p>
              </div>

              <div className="docs-card">
                <h4 className="docs-card-title">🔒 IT & Security Compliance</h4>
                <p className="docs-card-text">
                  Immediate lookup of VPN requirements, password rotation rules, multi-factor authentication (MFA) protocols, and device encryption standards.
                </p>
              </div>

              <div className="docs-card">
                <h4 className="docs-card-title">⚙️ Engineering & Architecture</h4>
                <p className="docs-card-text">
                  Quick verification of deployment checklists, server configurations, backup schedules, database replica requirements, and API constraints.
                </p>
              </div>
            </div>
          </section>
        )}

        {/* ==================== 2. GETTING STARTED GUIDE ==================== */}
        {activeCategory === 'how-to-use' && (
          <section className="docs-section">
            <div className="docs-section-intro">
              <h2 className="docs-section-heading">Getting Started: Step-by-Step Guide</h2>
              <p className="docs-section-sub">
                Follow this quick 4-step workflow to get the most out of your enterprise knowledge base.
              </p>
            </div>

            <div className="docs-grid-4">
              <div className="docs-card step-card">
                <div className="step-number">01</div>
                <h4 className="docs-card-title">Sign In</h4>
                <p className="docs-card-text">
                  Sign in with your Google Workspace account using the button at the top-right. This creates your isolated personal workspace and activates persistent chat history.
                </p>
                <div className="step-meta">
                  <Lock size={13} />
                  <span>Secure workspace isolation</span>
                </div>
              </div>

              <div className="docs-card step-card">
                <div className="step-number">02</div>
                <h4 className="docs-card-title">Upload Documents</h4>
                <p className="docs-card-text">
                  Open the <strong>Docs</strong> drawer inside Ask AI and upload your PDF manuals, handbooks, or specs. MARVO AI will index them in the background.
                </p>
                <div className="step-meta">
                  <UploadCloud size={13} />
                  <span>PDFs up to 50MB</span>
                </div>
              </div>

              <div className="docs-card step-card">
                <div className="step-number">03</div>
                <h4 className="docs-card-title">Ask Your Question</h4>
                <p className="docs-card-text">
                  Type your inquiry into the search bar. You can choose to search all documents or select a specific document using the Document Scope dropdown.
                </p>
                <div className="step-meta">
                  <MessageSquare size={13} />
                  <span>Natural language input</span>
                </div>
              </div>

              <div className="docs-card step-card">
                <div className="step-number">04</div>
                <h4 className="docs-card-title">Review & Verify</h4>
                <p className="docs-card-text">
                  Read the synthesized response, review side-by-side tables, and click citation pills ([1], [2]) to view the exact page and source passage.
                </p>
                <div className="step-meta">
                  <CheckCircle2 size={13} />
                  <span>Direct page references</span>
                </div>
              </div>
            </div>

            {/* Interface Guide */}
            <h3 className="docs-subheading" style={{ marginTop: '36px' }}>
              <Zap size={18} className="text-accent" />
              <span>Tour of the Interface</span>
            </h3>

            <div className="docs-grid-2">
              <div className="docs-card">
                <h4 className="docs-card-title">💬 Ask AI Main View</h4>
                <p className="docs-card-text">
                  Your primary research workspace. Features an intuitive search bar, suggested workplace prompt chips, document scope filtering, and a toggleable Document Manager drawer.
                </p>
              </div>

              <div className="docs-card">
                <h4 className="docs-card-title">📂 Document Manager Drawer</h4>
                <p className="docs-card-text">
                  Located directly within Ask AI. Shows all active documents in your library, their page count, indexing status (Ready / Processing), and options to upload new PDFs or remove old files.
                </p>
              </div>

              <div className="docs-card">
                <h4 className="docs-card-title">🕒 Chat History & Search</h4>
                <p className="docs-card-text">
                  Accessible from the sidebar. Reopen previous question threads, search prior conversations by keyword, or start a clean new discussion with a single click.
                </p>
              </div>

              <div className="docs-card">
                <h4 className="docs-card-title">⚙️ Workspace Settings</h4>
                <p className="docs-card-text">
                  Customize the look and feel of the platform with 3 tailored themes: Dark Theme (focus), Light Theme (clarity), or soothing Mint Green Theme.
                </p>
              </div>
            </div>
          </section>
        )}

        {/* ==================== 3. QUESTION & PROMPT GUIDE ==================== */}
        {activeCategory === 'prompting' && (
          <section className="docs-section">
            <div className="docs-section-intro">
              <h2 className="docs-section-heading">How to Ask Effective Questions</h2>
              <p className="docs-section-sub">
                Explore guidelines, query patterns, and copyable prompt examples to get the most accurate answers and side-by-side comparison tables.
              </p>
            </div>

            <div className="docs-faq-list">
              {filteredPrompts.map((item, idx) => {
                const isOpen = expandedPrompt === idx
                return (
                  <div key={item.id} className="docs-faq-item">
                    <button
                      className="docs-faq-question"
                      onClick={() => togglePrompt(idx)}
                      aria-expanded={isOpen}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                        <span className={`query-type-tag ${item.tagClass}`}>
                          {item.category}
                        </span>
                        <span>{item.q}</span>
                      </div>
                      {isOpen ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                    </button>

                    {isOpen && (
                      <div className="docs-faq-answer">
                        <p style={{ marginBottom: '12px' }}>{item.summary}</p>

                        <div className="query-example-box" style={{ marginBottom: '10px' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                            <span className="example-label">Example Prompt</span>
                            <button
                              className="copy-btn"
                              onClick={() => handleCopy(`prompt-${idx}`, item.example)}
                              title="Copy prompt to clipboard"
                            >
                              {copiedKey === `prompt-${idx}` ? <Check size={12} /> : <Copy size={12} />}
                              <span>{copiedKey === `prompt-${idx}` ? 'Copied' : 'Copy Prompt'}</span>
                            </button>
                          </div>
                          <div className="example-text">"{item.example}"</div>
                        </div>

                        <div className="query-feature-note">
                          💡 <strong>What MARVO AI does:</strong> {item.systemAction}
                        </div>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>

            {/* Scope Filter Callout */}
            <div className="docs-callout-box" style={{ marginTop: '20px' }}>
              <div className="callout-icon">
                <Filter size={20} />
              </div>
              <div className="callout-body">
                <h4 className="callout-title">Pro Tip: Targeted Searching with Document Scope</h4>
                <p className="callout-text">
                  If you already know that your question only relates to a specific manual (for instance, <code>Orbit_Security_Policy.pdf</code>), choose that file in the <strong>Document Scope</strong> dropdown before submitting your query. This ensures that MARVO AI focuses 100% of its attention on that document.
                </p>
              </div>
            </div>
          </section>
        )}

        {/* ==================== 4. DOCUMENT MANAGEMENT ==================== */}
        {activeCategory === 'document-mgmt' && (
          <section className="docs-section">
            <div className="docs-section-intro">
              <h2 className="docs-section-heading">Document Management & Best Practices</h2>
              <p className="docs-section-sub">
                How to upload, monitor, and maintain your workspace knowledge documents.
              </p>
            </div>

            <div className="docs-grid-3">
              <div className="docs-card">
                <div className="feature-icon-box">
                  <FileText size={18} />
                </div>
                <h4 className="docs-card-title">Supported Formats</h4>
                <p className="docs-card-text">
                  Standard PDF files containing selectable text or scanned pages. Ideal for handbooks, SOPs, agreements, policy memos, and architecture guides.
                </p>
                <div className="step-meta">
                  <span>File size limit: 50MB • Up to 150 pages</span>
                </div>
              </div>

              <div className="docs-card">
                <div className="feature-icon-box">
                  <UploadCloud size={18} />
                </div>
                <h4 className="docs-card-title">Uploading Documents</h4>
                <p className="docs-card-text">
                  Inside Ask AI, click the <strong>Docs</strong> button to open the document drawer. Drag and drop your PDF or click "Upload New PDF". Processing starts automatically in the background.
                </p>
                <div className="step-meta">
                  <span>Background processing (no waiting)</span>
                </div>
              </div>

              <div className="docs-card">
                <div className="feature-icon-box">
                  <CheckCircle2 size={18} />
                </div>
                <h4 className="docs-card-title">Document Status</h4>
                <p className="docs-card-text">
                  Each uploaded file shows a status badge: <strong>Processing</strong> (preparing your document) or <strong>Ready</strong> (fully searchable). Documents are ready to answer queries within seconds.
                </p>
                <div className="step-meta">
                  <span>Automatic status indicator</span>
                </div>
              </div>
            </div>

            {/* Best Practices for Document Quality */}
            <h3 className="docs-subheading" style={{ marginTop: '36px' }}>
              <ShieldCheck size={18} className="text-accent" />
              <span>Best Practices for Optimal Search Results</span>
            </h3>

            <div className="docs-grid-2">
              <div className="docs-card">
                <h4 className="docs-card-title">✅ Do: Use Descriptive Document Titles</h4>
                <p className="docs-card-text">
                  Name your PDF files descriptively (e.g., <code>Employee_Handbook_2026.pdf</code> rather than <code>Doc1_final_v3.pdf</code>). Clear filenames make citations in answers easy for your team to identify and trust.
                </p>
              </div>

              <div className="docs-card">
                <h4 className="docs-card-title">✅ Do: Remove Deprecated Document Versions</h4>
                <p className="docs-card-text">
                  When a new edition of a company policy is released, delete the obsolete PDF from your Document Drawer. This prevents conflicting answers between old and new guidelines.
                </p>
              </div>

              <div className="docs-card">
                <h4 className="docs-card-title">✅ Do: Upload Files with Clear Headings & Tables</h4>
                <p className="docs-card-text">
                  MARVO AI natively recognizes structured document outlines, bullet points, and tables. Clean formatting ensures comparative metrics and tables are extracted with 100% accuracy.
                </p>
              </div>

              <div className="docs-card">
                <h4 className="docs-card-title">⚠️ Avoid: Password-Protected PDFs</h4>
                <p className="docs-card-text">
                  Ensure uploaded PDFs are not encrypted with an opening password, as the ingestion system cannot read locked documents without credentials.
                </p>
              </div>
            </div>
          </section>
        )}

        {/* ==================== 5. CITATIONS & VERIFICATION ==================== */}
        {activeCategory === 'citations' && (
          <section className="docs-section">
            <div className="docs-section-intro">
              <h2 className="docs-section-heading">Citations & Verification System</h2>
              <p className="docs-section-sub">
                How to audit claims, read confidence ratings, and verify every answer against source pages.
              </p>
            </div>

            <div className="docs-hero-card">
              <div className="docs-hero-content">
                <span className="docs-pill-accent">Zero Hallucinations Guarantee</span>
                <h3 className="docs-hero-title">How Source Citations Work</h3>
                <p className="docs-hero-desc">
                  Every answer generated by MARVO AI includes inline citation pills (e.g. <code>[1]</code>, <code>[2]</code>) and a list of verified source references at the bottom of the answer card.
                </p>
              </div>
            </div>

            <div className="docs-grid-3">
              <div className="docs-card">
                <h4 className="docs-card-title">1. Document Name & Page Number</h4>
                <p className="docs-card-text">
                  Each citation displays the exact filename and page where the policy statement is located (e.g. <code>Orbit_Security_Policy.pdf • Page 3</code>).
                </p>
              </div>

              <div className="docs-card">
                <h4 className="docs-card-title">2. Verbatim Source Snippets</h4>
                <p className="docs-card-text">
                  Clicking on any citation pill reveals the exact excerpt extracted from the PDF, allowing you to read the context surrounding the answer.
                </p>
              </div>

              <div className="docs-card">
                <h4 className="docs-card-title">3. Confidence Level Rating</h4>
                <p className="docs-card-text">
                  Answers display a confidence badge (<strong>HIGH</strong> or <strong>MEDIUM</strong>) indicating how strongly the answer is corroborated by the source documentation.
                </p>
              </div>
            </div>

            {/* Simulated Answer Demonstration */}
            <h3 className="docs-subheading" style={{ marginTop: '36px' }}>
              <Eye size={18} className="text-accent" />
              <span>Example of an Answer with Citations</span>
            </h3>

            <div className="docs-card" style={{ borderLeft: '4px solid var(--accent-blue)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>
                  Question: "What is the remote work VPN protocol?"
                </span>
                <span style={{ fontSize: '11px', fontWeight: 700, color: '#10b981', background: 'rgba(16, 185, 129, 0.1)', padding: '2px 8px', borderRadius: '12px' }}>
                  HIGH confidence • 2 verified sources
                </span>
              </div>

              <p style={{ fontSize: '13.5px', color: 'var(--text-secondary)', lineHeight: '1.6' }}>
                All employees accessing internal systems from outside company facilities are required to connect via <strong>OrbitSecure VPN</strong> with multi-factor authentication (MFA) enabled. Split tunneling is strictly prohibited on managed laptops.
              </p>

              <div style={{ display: 'flex', gap: '8px', marginTop: '12px', flexWrap: 'wrap' }}>
                <span style={{ fontSize: '11.5px', padding: '4px 10px', borderRadius: '6px', background: 'var(--bg-pill)', border: '1px solid var(--border-subtle)', color: 'var(--accent-blue)', display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                  <strong>[1]</strong> Orbit_Security_Policy.pdf <span style={{ color: 'var(--text-muted)' }}>Page 2</span>
                </span>
                <span style={{ fontSize: '11.5px', padding: '4px 10px', borderRadius: '6px', background: 'var(--bg-pill)', border: '1px solid var(--border-subtle)', color: 'var(--text-secondary)', display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                  <strong>[2]</strong> Employee_Handbook_2026.pdf <span style={{ color: 'var(--text-muted)' }}>Page 14</span>
                </span>
              </div>
            </div>
          </section>
        )}

        {/* ==================== 6. DATA PRIVACY & FAQS ==================== */}
        {activeCategory === 'security-faq' && (
          <section className="docs-section">
            <div className="docs-section-intro">
              <h2 className="docs-section-heading">Data Privacy & Frequently Asked Questions</h2>
              <p className="docs-section-sub">
                Enterprise security commitments and answers to common user questions.
              </p>
            </div>

            {/* Privacy Pillars */}
            <div className="docs-grid-3">
              <div className="docs-card">
                <div className="feature-icon-box">
                  <Lock size={18} />
                </div>
                <h4 className="docs-card-title">Tenant Data Isolation</h4>
                <p className="docs-card-text">
                  Your uploaded documents, search queries, and chat history are bound strictly to your authenticated Google account and cannot be accessed by other users.
                </p>
              </div>

              <div className="docs-card">
                <div className="feature-icon-box">
                  <ShieldCheck size={18} />
                </div>
                <h4 className="docs-card-title">Zero Public Model Training</h4>
                <p className="docs-card-text">
                  Your proprietary enterprise information is strictly used for in-session retrieval and is never used to train or fine-tune public foundation models.
                </p>
              </div>

              <div className="docs-card">
                <div className="feature-icon-box">
                  <CheckCircle2 size={18} />
                </div>
                <h4 className="docs-card-title">Complete Data Control</h4>
                <p className="docs-card-text">
                  You maintain full ownership of your data. You can delete uploaded documents or clear saved conversations at any time with immediate effect.
                </p>
              </div>
            </div>

            {/* Accordion FAQs */}
            <h3 className="docs-subheading" style={{ marginTop: '36px' }}>
              <HelpCircle size={18} className="text-accent" />
              <span>Frequently Asked Questions</span>
            </h3>

            <div className="docs-faq-list">
              {filteredFaqs.map((faq, idx) => {
                const isOpen = expandedFaq === idx
                return (
                  <div key={idx} className="docs-faq-item">
                    <button
                      className="docs-faq-question"
                      onClick={() => toggleFaq(idx)}
                      aria-expanded={isOpen}
                    >
                      <span>{faq.q}</span>
                      {isOpen ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                    </button>
                    {isOpen && (
                      <div className="docs-faq-answer">
                        <p>{faq.a}</p>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </section>
        )}
      </main>
    </div>
  )
}
