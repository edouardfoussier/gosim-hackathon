// Verdict Card — three variants: phishing / suspicious / safe
// Floating card; 18pt+ body; 56pt action buttons.
// No padlock icons, no DANGER copy, no bevels.

const V_W = 760;
const V_H = 980;

const v_cream = '#fbf7f0';
const v_ink = '#1f1a14';
const v_muted = 'rgba(31,26,20,0.6)';
const v_subtle = 'rgba(31,26,20,0.4)';

const TONES = {
  phishing: {
    name: 'Phishing',
    chip: 'high confidence',
    headline: "I don't think this is really from your bank.",
    subhead: "Don't click anything in this email. Don't reply. I'll help.",
    bannerBg: 'linear-gradient(135deg, #d44a2a 0%, #b8351c 60%, #8a2412 100%)',
    bannerInk: '#fff5ec',
    accent: '#b8351c',
    accentSoft: 'rgba(184,53,28,0.10)',
    accentLine: 'rgba(184,53,28,0.22)',
    glyph: '!',
    primaryAction: 'Tell Lisa about this',
    secondaryAction: 'Archive it for me',
    tertiaryAction: 'Show me the technical details',
    primaryStyle: 'firm',
  },
  suspicious: {
    name: 'Suspicious',
    chip: 'low confidence',
    headline: "Something here looks a little off.",
    subhead: "It might be fine, but I'd ask before opening any links.",
    bannerBg: 'linear-gradient(135deg, #e9a259 0%, #d97a25 60%, #a55a18 100%)',
    bannerInk: '#fff8eb',
    accent: '#a55a18',
    accentSoft: 'rgba(217,122,37,0.10)',
    accentLine: 'rgba(217,122,37,0.22)',
    glyph: '?',
    primaryAction: 'Archive it for me',
    secondaryAction: 'Tell Lisa about this',
    tertiaryAction: 'Show me the technical details',
    primaryStyle: 'firm',
  },
  safe: {
    name: 'Safe',
    chip: null,
    headline: "This looks fine to me.",
    subhead: null,
    bannerBg: 'linear-gradient(135deg, #4a8a55 0%, #2f6d3f 60%, #1f4a2a 100%)',
    bannerInk: '#f1f7ec',
    accent: '#2f6d3f',
    accentSoft: 'rgba(47,109,63,0.10)',
    accentLine: 'rgba(47,109,63,0.22)',
    glyph: '✓',
    primaryAction: null,
    secondaryAction: null,
    tertiaryAction: 'Show me why',
    primaryStyle: 'firm',
  },
};

const SIGNS_PHISH = [
  { tactic: 'authority', text: <>The sender is <code style={cstyle}>aetnna-secure.com</code>, not <code style={cstyle}>aetna.com</code> — one letter different. A real insurer wouldn't send from a slightly-misspelled address.</> },
  { tactic: 'urgency', text: <>The link inside takes you through 4 redirects to a server in Russia, then asks for your Social Security number. No insurer asks for that by email.</> },
  { tactic: 'social_proof', text: <>The same template was reported to the FTC twelve times last week. People are flagging it as a scam, not a real bill.</> },
];

const SIGNS_SUS = [
  { tactic: 'urgency', text: <>The email says you must act within 24 hours, but no deadline is mentioned anywhere on the company's website.</> },
  { tactic: 'authority', text: <>The signature says "Apple Support" but the address ends in <code style={cstyle}>@mailer-prom.io</code>. That's not an Apple domain.</> },
];

const cstyle = {
  fontFamily: '"JetBrains Mono", ui-monospace, SFMono-Regular, monospace',
  fontSize: '0.92em',
  background: 'rgba(31,26,20,0.06)',
  padding: '2px 6px',
  borderRadius: 4,
};

function VerdictCard({ variant = 'phishing', signs = null, scale = 1 }) {
  const t = TONES[variant];
  const useSigns = signs || (variant === 'phishing' ? SIGNS_PHISH : variant === 'suspicious' ? SIGNS_SUS : []);

  if (variant === 'safe') return <SafeCard tone={t} scale={scale} />;

  return (
    <div style={{
      width: V_W, height: V_H, background: v_cream,
      borderRadius: 28, overflow: 'hidden',
      boxShadow: '0 30px 80px rgba(122,60,28,0.18), 0 6px 20px rgba(122,60,28,0.10), 0 0 0 1px rgba(31,26,20,0.04)',
      fontFamily: 'Inter, sans-serif', color: v_ink,
      display: 'flex', flexDirection: 'column',
      fontSize: 18 * scale,
    }}>
      {/* banner */}
      <div style={{
        background: t.bannerBg, color: t.bannerInk,
        padding: '36px 44px 38px',
        position: 'relative', overflow: 'hidden',
      }}>
        {/* soft glow */}
        <div style={{
          position: 'absolute', right: -120, top: -120, width: 380, height: 380,
          borderRadius: '50%', background: 'radial-gradient(circle, rgba(255,255,255,0.18), transparent 65%)',
        }} />

        <div style={{ position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ fontSize: 13, letterSpacing: '0.18em', textTransform: 'uppercase', opacity: 0.85, fontWeight: 500 }}>
            Xiexie has read this email
          </div>
          {t.chip && (
            <div style={{
              fontSize: 13, padding: '6px 14px', borderRadius: 999,
              background: 'rgba(0,0,0,0.18)', backdropFilter: 'blur(8px)',
              color: t.bannerInk, letterSpacing: '0.04em',
              border: '0.5px solid rgba(255,255,255,0.18)',
            }}>{t.chip}</div>
          )}
        </div>

        <div style={{ position: 'relative', display: 'flex', alignItems: 'flex-start', gap: 22, marginTop: 22 }}>
          <BannerGlyph char={t.glyph} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{
              fontFamily: 'Fraunces, serif', fontSize: 32, fontWeight: 500,
              letterSpacing: -0.6, lineHeight: 1.05,
              color: t.bannerInk,
              opacity: 0.9, marginBottom: 4,
            }}>
              {t.name}
            </div>
            <div style={{
              fontFamily: 'Fraunces, serif', fontSize: 38, lineHeight: 1.18,
              fontWeight: 400, letterSpacing: -0.4, textWrap: 'pretty',
            }}>
              {t.headline}
            </div>
            {t.subhead && (
              <div style={{ marginTop: 14, fontSize: 19, lineHeight: 1.5, opacity: 0.92 }}>
                {t.subhead}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* signs */}
      <div style={{ padding: '32px 44px 16px', flex: 1, display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{ fontSize: 13, letterSpacing: '0.18em', textTransform: 'uppercase', color: v_subtle, fontWeight: 600, marginBottom: 4 }}>
          Why I think so
        </div>
        {useSigns.map((s, i) => <SignCard key={i} sign={s} tone={t} index={i + 1} />)}
      </div>

      {/* actions */}
      <div style={{ padding: '8px 44px 36px', display: 'flex', flexDirection: 'column', gap: 10 }}>
        {t.primaryAction && <ActionButton label={t.primaryAction} kind="primary" tone={t} />}
        {t.secondaryAction && <ActionButton label={t.secondaryAction} kind="secondary" tone={t} />}
        {t.tertiaryAction && <ActionButton label={t.tertiaryAction} kind="ghost" tone={t} />}
      </div>
    </div>
  );
}

function SafeCard({ tone, scale = 1 }) {
  return (
    <div style={{
      width: V_W, height: V_H, background: v_cream,
      borderRadius: 28, overflow: 'hidden',
      boxShadow: '0 30px 80px rgba(47,109,63,0.14), 0 6px 20px rgba(47,109,63,0.08), 0 0 0 1px rgba(31,26,20,0.04)',
      fontFamily: 'Inter, sans-serif', color: v_ink,
      display: 'flex', flexDirection: 'column', justifyContent: 'space-between',
      fontSize: 18 * scale,
    }}>
      {/* banner */}
      <div style={{
        background: tone.bannerBg, color: tone.bannerInk,
        padding: '36px 44px 38px', position: 'relative', overflow: 'hidden',
      }}>
        <div style={{
          position: 'absolute', right: -120, top: -120, width: 380, height: 380,
          borderRadius: '50%', background: 'radial-gradient(circle, rgba(255,255,255,0.18), transparent 65%)',
        }} />
        <div style={{ position: 'relative', fontSize: 13, letterSpacing: '0.18em', textTransform: 'uppercase', opacity: 0.85, fontWeight: 500 }}>
          Xiexie has read this email
        </div>
        <div style={{ position: 'relative', display: 'flex', alignItems: 'center', gap: 22, marginTop: 22 }}>
          <BannerGlyph char={tone.glyph} />
          <div style={{ flex: 1 }}>
            <div style={{
              fontFamily: 'Fraunces, serif', fontSize: 32, fontWeight: 500,
              letterSpacing: -0.6, lineHeight: 1.05, opacity: 0.9, marginBottom: 4,
            }}>
              {tone.name}
            </div>
            <div style={{
              fontFamily: 'Fraunces, serif', fontSize: 38, lineHeight: 1.18,
              fontWeight: 400, letterSpacing: -0.4,
            }}>
              {tone.headline}
            </div>
          </div>
        </div>
      </div>

      {/* body — quiet */}
      <div style={{ padding: '40px 44px', flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 24 }}>
        <div style={{ fontSize: 22, lineHeight: 1.5, color: v_muted, textWrap: 'pretty' }}>
          The sender, the links, and the signing checks all match what I'd expect.
          You can read it without worrying.
        </div>

        <div style={{
          display: 'flex', alignItems: 'center', gap: 14,
          padding: '18px 22px', borderRadius: 16,
          background: tone.accentSoft, border: `0.5px solid ${tone.accentLine}`,
        }}>
          <div style={{
            width: 10, height: 10, borderRadius: '50%', background: tone.accent,
            boxShadow: `0 0 0 4px ${tone.accentSoft}`,
          }} />
          <div style={{ fontSize: 17, color: v_ink }}>
            From <strong style={{ fontWeight: 600 }}>Lisa Chen</strong> · Domain check passed · Signing valid
          </div>
        </div>
      </div>

      <div style={{ padding: '0 44px 36px' }}>
        <ActionButton label={tone.tertiaryAction} kind="ghost" tone={tone} />
      </div>
    </div>
  );
}

function BannerGlyph({ char }) {
  return (
    <div style={{
      width: 80, height: 80, borderRadius: 22, flexShrink: 0,
      background: 'rgba(0,0,0,0.18)',
      backdropFilter: 'blur(8px)',
      border: '0.5px solid rgba(255,255,255,0.22)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      fontFamily: 'Fraunces, serif', fontSize: 50, fontWeight: 500, lineHeight: 1,
      color: 'currentColor',
    }}>
      {char}
    </div>
  );
}

const TACTIC_LABEL = {
  authority: 'authority',
  urgency: 'urgency',
  social_proof: 'social proof',
  scarcity: 'scarcity',
};

function SignCard({ sign, tone, index }) {
  return (
    <div style={{
      background: '#fff', borderRadius: 20, padding: '20px 24px',
      border: '0.5px solid rgba(31,26,20,0.06)',
      boxShadow: '0 1px 0 rgba(31,26,20,0.03), 0 8px 24px rgba(122,60,28,0.06)',
      display: 'flex', gap: 18, position: 'relative',
    }}>
      <div style={{
        flexShrink: 0, width: 32, height: 32, borderRadius: 10,
        background: tone.accentSoft, color: tone.accent,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontFamily: 'Fraunces, serif', fontSize: 18, fontWeight: 500,
      }}>{index}</div>
      <div style={{ flex: 1, minWidth: 0, paddingRight: 70 }}>
        <div style={{ fontSize: 18, lineHeight: 1.5, color: v_ink, textWrap: 'pretty' }}>
          {sign.text}
        </div>
      </div>
      <div style={{
        position: 'absolute', top: 18, right: 22,
        fontSize: 11, padding: '4px 9px', borderRadius: 999,
        background: tone.accentSoft, color: tone.accent,
        letterSpacing: '0.12em', textTransform: 'uppercase', fontWeight: 600,
        border: `0.5px solid ${tone.accentLine}`,
      }}>{TACTIC_LABEL[sign.tactic]}</div>
    </div>
  );
}

function ActionButton({ label, kind, tone }) {
  const base = {
    width: '100%', height: 56,
    borderRadius: 16, border: 'none',
    fontFamily: 'Inter, sans-serif',
    fontSize: 19, fontWeight: 500, letterSpacing: -0.1,
    cursor: 'default', textAlign: 'center', padding: '0 20px',
    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10,
  };
  if (kind === 'primary') {
    return (
      <button style={{
        ...base,
        background: tone.accent, color: '#fff8eb',
        boxShadow: `0 1px 0 rgba(255,255,255,0.2) inset, 0 6px 14px ${tone.accentSoft}, 0 0 0 1px ${tone.accent}`,
      }}>{label}</button>
    );
  }
  if (kind === 'secondary') {
    return (
      <button style={{
        ...base,
        background: '#fff', color: v_ink,
        border: '0.5px solid rgba(31,26,20,0.16)',
        boxShadow: '0 1px 2px rgba(31,26,20,0.04)',
      }}>{label}</button>
    );
  }
  return (
    <button style={{
      ...base, background: 'transparent', color: v_muted,
      fontSize: 17, height: 48, fontWeight: 500,
      textDecoration: 'underline', textUnderlineOffset: 4, textDecorationColor: 'rgba(31,26,20,0.25)',
    }}>{label}</button>
  );
}

Object.assign(window, { VerdictCard });
