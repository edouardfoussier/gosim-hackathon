// Overlay glyph references — Phishing / Suspicious / Safe.
// 48x48 native, scaled up for visibility on the canvas. Modern flat,
// one warm soft glow on the phishing variant only.

function GlyphCard({ kind }) {
  const cfg = {
    phishing: {
      name: 'Phishing',
      hex: '#b8351c',
      label: 'Rounded triangle, white !, slow pulse glow (1.4s).',
    },
    suspicious: {
      name: 'Suspicious',
      hex: '#d97a25',
      label: 'Circle, white ?, gentle bob (2s).',
    },
    safe: {
      name: 'Safe',
      hex: '#2f6d3f',
      label: 'Circle, white ✓, no animation.',
    },
  }[kind];

  return (
    <div style={{
      width: 360, height: 480, padding: '36px 32px 32px', boxSizing: 'border-box',
      background: '#fbf7f0', borderRadius: 24,
      display: 'flex', flexDirection: 'column', justifyContent: 'space-between',
      fontFamily: 'Inter, sans-serif', color: '#1f1a14',
      boxShadow: '0 6px 20px rgba(122,60,28,0.06), 0 0 0 1px rgba(31,26,20,0.04)',
    }}>
      <div style={{ fontSize: 12, letterSpacing: '0.18em', textTransform: 'uppercase', color: 'rgba(31,26,20,0.5)', fontWeight: 600 }}>
        {cfg.name}
      </div>

      <div style={{
        flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
        position: 'relative',
      }}>
        {/* checkered transparent canvas */}
        <div style={{
          width: 240, height: 240, borderRadius: 16, position: 'relative',
          background:
            'repeating-conic-gradient(rgba(31,26,20,0.04) 0% 25%, transparent 0% 50%) 0 0 / 24px 24px',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <div className={`xx-glyph xx-${kind}`}>
            <Glyph kind={kind} hex={cfg.hex} />
          </div>
        </div>
      </div>

      <div style={{ fontSize: 13, color: 'rgba(31,26,20,0.6)', lineHeight: 1.5, fontFamily: '"JetBrains Mono", ui-monospace, monospace' }}>
        {cfg.label} · 48×48
      </div>
    </div>
  );
}

function Glyph({ kind, hex }) {
  const size = 144; // 3× the production 48px so the canvas reads at zoom 1
  if (kind === 'phishing') {
    return (
      <svg width={size} height={size} viewBox="0 0 48 48" style={{ filter: `drop-shadow(0 0 6px ${hex}66)` }}>
        <path
          d="M24 5.4 L43 39.6 Q44.2 41.7 41.8 41.7 L6.2 41.7 Q3.8 41.7 5 39.6 Z"
          fill={hex}
        />
        <rect x="22.5" y="17" width="3" height="13" rx="1.5" fill="#fff8eb" />
        <circle cx="24" cy="34" r="1.8" fill="#fff8eb" />
      </svg>
    );
  }
  if (kind === 'suspicious') {
    return (
      <svg width={size} height={size} viewBox="0 0 48 48">
        <circle cx="24" cy="24" r="19" fill={hex} />
        <text x="24" y="32.5" textAnchor="middle" fontFamily="Inter, sans-serif" fontSize="22" fontWeight="600" fill="#fff8eb">?</text>
      </svg>
    );
  }
  return (
    <svg width={size} height={size} viewBox="0 0 48 48">
      <circle cx="24" cy="24" r="19" fill={hex} />
      <path d="M14 24.5 L21 31.5 L34 17.5" stroke="#f1f7ec" strokeWidth="3.4" strokeLinecap="round" strokeLinejoin="round" fill="none" />
    </svg>
  );
}

// Inject animation styles once
if (typeof document !== 'undefined' && !document.getElementById('xx-glyph-styles')) {
  const s = document.createElement('style');
  s.id = 'xx-glyph-styles';
  s.textContent = `
    .xx-glyph { display: inline-block; }
    .xx-phishing { animation: xx-pulse 1.4s ease-in-out infinite; }
    .xx-suspicious { animation: xx-bob 2s ease-in-out infinite; }
    @keyframes xx-pulse {
      0%, 100% { filter: drop-shadow(0 0 6px rgba(184,53,28,0.45)); transform: scale(1); }
      50%      { filter: drop-shadow(0 0 16px rgba(184,53,28,0.85)); transform: scale(1.04); }
    }
    @keyframes xx-bob {
      0%, 100% { transform: translateY(0); }
      50%      { transform: translateY(-4px); }
    }
  `;
  document.head.appendChild(s);
}

Object.assign(window, { GlyphCard });
