import React from 'react'
import { FileText } from 'lucide-react'

// Authentic brand icons matching the user's screenshot
export function SlackBrandIcon({ size = 18 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 128 128" fill="none">
      <path d="M26.4 78.4a13 13 0 1 1-13-13h13v13zm6.6 0a13 13 0 1 1 26 0v32.6a13 13 0 1 1-26 0V78.4z" fill="#E01E5A" />
      <path d="M49.6 26.4a13 13 0 1 1 13-13v13h-13zm0 6.6a13 13 0 1 1 0 26H17a13 13 0 1 1 0-26h32.6z" fill="#36C5F0" />
      <path d="M101.6 49.6a13 13 0 1 1 13 13h-13v-13zm-6.6 0a13 13 0 1 1-26 0V17a13 13 0 1 1 26 0v32.6z" fill="#2EB67D" />
      <path d="M78.4 101.6a13 13 0 1 1-13 13v-13h13zm0-6.6a13 13 0 1 1 0-26H111a13 13 0 1 1 0 26H78.4z" fill="#ECB22E" />
    </svg>
  )
}

export function NotionBrandIcon({ size = 18 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 100 100" fill="currentColor">
      <rect x="15" y="15" width="70" height="70" rx="14" fill="#202534" />
      <path
        d="M32 30h11.2l20.4 29.5V30H72v40H60.8L40.4 40.5V70H32V30z"
        fill="#FFFFFF"
      />
    </svg>
  )
}

export function GoogleDriveBrandIcon({ size = 18 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 87.3 78" fill="none">
      <path d="m6.6 66.85 3.85 6.65c.8 1.4 1.95 2.5 3.3 3.3l13.75-23.8H6.6c0 1.55.4 3.1 1.2 4.45l-1.2 9.4z" fill="#0066DA" />
      <path d="m43.65 25-13.75-23.8c-1.35.8-2.5 1.9-3.3 3.3l-25.4 44c-.8 1.35-1.2 2.9-1.2 4.45h20.9z" fill="#00AC47" />
      <path d="m73.55 76.8c1.35-.8 2.5-1.9 3.3-3.3l1.6-2.75 7.65-13.25c.8-1.35 1.2-2.9 1.2-4.5H66.4l4.5 7.8z" fill="#EA4335" />
      <path d="m43.65 25 13.75-23.8c-1.35-.8-2.9-1.2-4.45-1.2H34.35c-1.55 0-3.1.4-4.45 1.2z" fill="#00832D" />
      <path d="m59.95 53-16.3-28-16.3 28h32.6z" fill="#2684FC" />
      <path d="m73.55 76.8c1.55 0 3.1-.4 4.45-1.2l-14.9-25.8-13.75 23.8c1.35.8 2.9 1.2 4.45 1.2h19.75z" fill="#FFBA00" />
    </svg>
  )
}

export function ConfluenceBrandIcon({ size = 18 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <path d="M2.5 17.5C1.6 16.1 1.6 14.3 2.5 12.9L6.2 7.3C7.1 5.9 8.6 5 10.3 5H13.7C12.4 6.3 11.6 8.1 11.6 10C11.6 11.9 12.4 13.7 13.7 15L10.3 19H7.1C5.2 19 3.4 18.4 2.5 17.5Z" fill="#0052CC" opacity="0.8" />
      <path d="M21.5 6.5C22.4 7.9 22.4 9.7 21.5 11.1L17.8 16.7C16.9 18.1 15.4 19 13.7 19H10.3C11.6 17.7 12.4 15.9 12.4 14C12.4 12.1 11.6 10.3 10.3 9L13.7 5H16.9C18.8 5 20.6 5.6 21.5 6.5Z" fill="#2684FF" />
    </svg>
  )
}

export function SharePointBrandIcon({ size = 18 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <circle cx="15.5" cy="8.5" r="5" fill="#038387" />
      <circle cx="8.5" cy="12.5" r="5.5" fill="#0078D4" />
      <circle cx="14" cy="16" r="4.5" fill="#107C41" />
    </svg>
  )
}

export function PdfBrandIcon({ size = 18 }) {
  return (
    <div style={{
      width: size,
      height: size,
      borderRadius: '4px',
      background: '#dc2626',
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      color: '#fff',
      fontSize: '8px',
      fontWeight: 800,
      letterSpacing: '-0.3px',
      flexShrink: 0
    }}>
      PDF
    </div>
  )
}

export function InternalDocsIcon({ size = 18 }) {
  return (
    <div style={{
      width: size,
      height: size,
      borderRadius: '4px',
      background: '#2563eb',
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      color: '#fff',
      flexShrink: 0
    }}>
      <FileText size={Math.round(size * 0.7)} color="#fff" />
    </div>
  )
}

export function renderSourceTypeIcon(type, size = 18) {
  switch (type) {
    case 'Slack':
      return <SlackBrandIcon size={size} />
    case 'Notion':
      return <NotionBrandIcon size={size} />
    case 'Google Drive':
      return <GoogleDriveBrandIcon size={size} />
    case 'Confluence':
      return <ConfluenceBrandIcon size={size} />
    case 'SharePoint':
      return <SharePointBrandIcon size={size} />
    case 'PDF Documents':
      return <PdfBrandIcon size={size} />
    case 'Internal Docs':
      return <InternalDocsIcon size={size} />
    default:
      return <FileText size={size} color="#3b82f6" />
  }
}

export const AVATARS = {
  'Olivia Rhye': 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=100&h=100&fit=crop&crop=face',
  'Noah Levin': 'https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?w=100&h=100&fit=crop&crop=face',
  'Liam Chen': 'https://images.unsplash.com/photo-1570295999919-56ceb5ecca61?w=100&h=100&fit=crop&crop=face',
  'Emma Davis': 'https://images.unsplash.com/photo-1580489944761-15a19d654956?w=100&h=100&fit=crop&crop=face'
}
