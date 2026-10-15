import React, { useId } from 'react';

/**
 * MarvoLogo - Official MARVO Logo component built from the exact SVG specification.
 *
 * @param {number} size - Scaling size in pixels (default: 32).
 * @param {boolean} withText - If true, renders the full 800x550 emblem with 'MARVO' + 'AI' badge.
 *                             If false, renders the cropped 'M' icon mark for headers and navigation.
 * @param {string} className - Optional CSS classes.
 * @param {boolean} glow - Whether to apply soft neon bloom filter.
 */
export default function MarvoLogo({
  size = 32,
  withText = false,
  className = '',
  glow = true,
  style = {},
  ...props
}) {
  const rawId = useId();
  const id = rawId.replace(/[^a-zA-Z0-9_-]/g, '');

  const leftGradId = `leftGrad-${id}`;
  const rightGradId = `rightGrad-${id}`;
  const pillarGradId = `pillarGrad-${id}`;
  const boxGradId = `boxGrad-${id}`;
  const glowFilterId = `glow-${id}`;

  const calculatedHeight = withText
    ? Math.round((size * 550) / 800)
    : Math.round((size * 260) / 280);

  const viewBox = withText ? '0 0 800 550' : '260 85 280 260';

  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox={viewBox}
      width={size}
      height={calculatedHeight}
      fill="none"
      className={`marvo-logo-mark ${className}`}
      style={{
        overflow: 'visible',
        display: 'inline-block',
        verticalAlign: 'middle',
        flexShrink: 0,
        transition: 'transform 0.28s cubic-bezier(0.16, 1, 0.3, 1), filter 0.28s ease',
        ...style,
      }}
      aria-label="MARVO Logo"
      role="img"
      {...props}
    >
      <defs>
        <style>{`
          @import url('https://fonts.googleapis.com/css2?family=Michroma&family=Orbitron:wght@700;800&display=swap');
          .marvo-svg-brand-text {
            font-family: 'Michroma', 'Orbitron', var(--font-sans), sans-serif;
            font-weight: 800;
            font-size: 62px;
            fill: var(--brand-marvo-color, #FFFFFF);
            letter-spacing: 6px;
          }
          .marvo-svg-ai-text {
            font-family: 'Orbitron', var(--font-sans), sans-serif;
            font-weight: 700;
            font-size: 46px;
            fill: #38BDF8;
            letter-spacing: 3px;
          }
        `}</style>

        {/* Left Wing Gradient (Deep Blue to Cyan) */}
        <linearGradient id={leftGradId} x1="260" y1="90" x2="420" y2="330" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#38BDF8" />
          <stop offset="50%" stopColor="#2563EB" />
          <stop offset="100%" stopColor="#1E1B4B" />
        </linearGradient>

        {/* Right Ribbon Gradient (Vibrant Purple to Cyan) */}
        <linearGradient id={rightGradId} x1="350" y1="260" x2="530" y2="90" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#6366F1" />
          <stop offset="45%" stopColor="#C084FC" />
          <stop offset="100%" stopColor="#2DD4BF" />
        </linearGradient>

        {/* Outer Right Pillar Gradient */}
        <linearGradient id={pillarGradId} x1="510" y1="90" x2="510" y2="330" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#60A5FA" />
          <stop offset="50%" stopColor="#2DD4BF" />
          <stop offset="100%" stopColor="#1E293B" />
        </linearGradient>

        {/* AI Box Border Gradient */}
        <linearGradient id={boxGradId} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#38BDF8" stopOpacity="0.9" />
          <stop offset="50%" stopColor="#38BDF8" stopOpacity="0.15" />
          <stop offset="100%" stopColor="#38BDF8" stopOpacity="0.9" />
        </linearGradient>

        {/* Soft Neon Glow Filter */}
        {glow && (
          <filter id={glowFilterId} x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="4.5" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>
        )}
      </defs>

      {/* ================= 'M' ICON GEOMETRY ================= */}
      <g transform="translate(0, 15)">
        {/* Left Outer & Inner Monogram Structure */}
        <path
          d="M 275 80 L 395 190 L 373 212 L 307 152 L 307 285 C 307 305, 275 305, 275 285 Z"
          fill={`url(#${leftGradId})`}
          stroke="#60A5FA"
          strokeWidth="1.5"
        />

        {/* Inner Left Fold */}
        <path
          d="M 322 185 L 385 242 C 395 250, 405 250, 415 242 L 400 262 C 385 272, 370 265, 355 252 L 345 242 L 345 285 C 345 318, 275 318, 275 285 L 307 285 C 307 295, 322 295, 322 285 Z"
          fill={`url(#${leftGradId})`}
          opacity="0.9"
        />

        {/* Right Outer Pillar */}
        <path
          d="M 525 80 L 525 285 C 525 318, 465 318, 465 285 L 465 205 L 493 178 L 493 278 C 493 292, 502 292, 502 278 L 502 102 Z"
          fill={`url(#${pillarGradId})`}
          stroke="#5EEAD4"
          strokeWidth="1.5"
        />

        {/* Center Interlocking Purple/Cyan Ribbon */}
        <path
          d="M 322 185 L 382 238 C 392 246, 402 246, 412 236 L 525 125 L 525 80 L 398 205 C 392 210, 386 210, 380 205 L 345 173 Z"
          fill={`url(#${rightGradId})`}
          filter={glow ? `url(#${glowFilterId})` : undefined}
        />

        {/* Lower Sweeping Purple Ribbon Curve */}
        <path
          d="M 345 225 C 375 262, 405 262, 435 230 L 493 172 L 493 202 L 442 252 C 408 284, 375 280, 345 245 Z"
          fill={`url(#${rightGradId})`}
        />

        {/* Glowing AI Circuit Nodes & Accents */}
        <line
          x1="322"
          y1="215"
          x2="365"
          y2="255"
          stroke="#E0F2FE"
          strokeWidth="2"
          filter={glow ? `url(#${glowFilterId})` : undefined}
        />
        <line
          x1="420"
          y1="230"
          x2="525"
          y2="125"
          stroke="#E0F2FE"
          strokeWidth="2.5"
          filter={glow ? `url(#${glowFilterId})` : undefined}
        />

        {/* Light Nodes (Dots) */}
        <circle cx="322" cy="215" r="4" fill="#FFFFFF" filter={glow ? `url(#${glowFilterId})` : undefined} />
        <circle cx="352" cy="243" r="3.5" fill="#FFFFFF" filter={glow ? `url(#${glowFilterId})` : undefined} />
        <circle cx="525" cy="125" r="5" fill="#FFFFFF" filter={glow ? `url(#${glowFilterId})` : undefined} />
        <circle cx="378" cy="175" r="3" fill="#38BDF8" filter={glow ? `url(#${glowFilterId})` : undefined} />
      </g>

      {/* ================= TYPOGRAPHY SECTION (Full Emblem Mode) ================= */}
      {withText && (
        <g transform="translate(0, 20)">
          {/* "MARVO" Text */}
          <text x="115" y="445" className="marvo-svg-brand-text">
            MARVO
          </text>

          {/* "AI" Badge Container */}
          <rect
            x="565"
            y="392"
            width="105"
            height="68"
            rx="14"
            fill="none"
            stroke={`url(#${boxGradId})`}
            strokeWidth="3"
            filter={glow ? `url(#${glowFilterId})` : undefined}
          />

          {/* Top-Right Corner Spark on AI Box */}
          <circle cx="666" cy="396" r="3.5" fill="#FFFFFF" filter={glow ? `url(#${glowFilterId})` : undefined} />

          {/* "AI" Text */}
          <text
            x="583"
            y="443"
            className="marvo-svg-ai-text"
            filter={glow ? `url(#${glowFilterId})` : undefined}
          >
            AI
          </text>
        </g>
      )}
    </svg>
  );
}
