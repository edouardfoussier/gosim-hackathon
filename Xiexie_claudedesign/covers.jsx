// Cover slide directions for the Xiexie deck.
// Three takes — same brand, different rhetorical lean.

const COVER_W = 1280;
const COVER_H = 720;

const cream = '#fbf7f0';
const ink = '#1f1a14';
const ember = '#d97a25';
const muted = 'rgba(31,26,20,0.55)';

// ─────────────────────────────────────────────────────────────
// Cover A · Hearth
// Quiet warm gradient. The whole slide is the feeling.
// ─────────────────────────────────────────────────────────────
function CoverHearth() {
  return (
    <div style={{
      width: COVER_W, height: COVER_H, position: 'relative', overflow: 'hidden',
      background: 'radial-gradient(ellipse 75% 60% at 30% 80%, #f4c98a 0%, #e9a259 22%, #d97a25 42%, #8a3a14 70%, #2a1408 100%)',
      fontFamily: 'Inter, sans-serif', color: cream,
    }}>
      {/* soft inner glow */}
      <div style={{
        position: 'absolute', left: '20%', top: '60%', width: 600, height: 600,
        borderRadius: '50%', background: 'radial-gradient(circle, rgba(255,220,170,0.35), transparent 60%)',
        filter: 'blur(40px)',
      }} />
      {/* tiny ember dot */}
      <div style={{
        position: 'absolute', left: '28%', top: '78%', width: 14, height: 14, borderRadius: '50%',
        background: '#fff3d6', boxShadow: '0 0 30px 8px rgba(255,220,150,0.7)',
      }} />

      {/* content */}
      <div style={{ position: 'absolute', inset: 0, padding: '64px 80px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', fontSize: 14, letterSpacing: '0.18em', textTransform: 'uppercase', opacity: 0.75 }}>
          <span>谢谢 · Xiexie</span>
          <span>GOSIM Paris · 2026</span>
        </div>
        <div>
          <div style={{ fontFamily: 'Fraunces, serif', fontSize: 132, lineHeight: 0.95, letterSpacing: -3, fontWeight: 400, fontVariationSettings: '"SOFT" 100, "opsz" 144' }}>
            The AI grandchild
          </div>
          <div style={{ fontFamily: 'Fraunces, serif', fontSize: 132, lineHeight: 0.95, letterSpacing: -3, fontWeight: 400, fontStyle: 'italic', fontVariationSettings: '"SOFT" 100, "opsz" 144', opacity: 0.85 }}>
            who never sleeps.
          </div>
          <div style={{ marginTop: 36, fontSize: 19, lineHeight: 1.5, maxWidth: 620, opacity: 0.82 }}>
            A voice-first companion that protects elderly users from online scams.
            Local-first. Open source. Built on GLM-5.1.
          </div>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// Cover B · Bilingual lockup
// 谢谢 as the hero. Confident, almost a poster.
// ─────────────────────────────────────────────────────────────
function CoverBilingual() {
  return (
    <div style={{
      width: COVER_W, height: COVER_H, position: 'relative', overflow: 'hidden',
      background: cream, color: ink, fontFamily: 'Inter, sans-serif',
    }}>
      {/* faint paper grain via repeating gradient */}
      <div style={{
        position: 'absolute', inset: 0, opacity: 0.4, pointerEvents: 'none',
        background: 'radial-gradient(circle at 20% 20%, rgba(217,122,37,0.08), transparent 50%), radial-gradient(circle at 85% 85%, rgba(217,122,37,0.06), transparent 50%)',
      }} />

      {/* top strip: small lockup + meta */}
      <div style={{ position: 'absolute', top: 56, left: 80, right: 80, display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 14, color: muted, letterSpacing: '0.08em' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <div style={{ width: 8, height: 8, borderRadius: '50%', background: ember }} />
          <span style={{ fontWeight: 500, color: ink }}>Xiexie</span>
          <span style={{ opacity: 0.5 }}>·</span>
          <span>An AI companion for elders</span>
        </div>
        <div style={{ fontVariantNumeric: 'tabular-nums' }}>v0.1 · GOSIM 2026</div>
      </div>

      {/* big bilingual hero */}
      <div style={{
        position: 'absolute', left: 80, top: 130, right: 80, bottom: 180,
        display: 'flex', alignItems: 'center', gap: 52,
      }}>
        <div style={{
          fontFamily: '"Noto Serif SC", "Songti SC", serif',
          fontSize: 480, lineHeight: 0.85, color: ember, fontWeight: 500,
          letterSpacing: -8,
          textShadow: '0 6px 28px rgba(217,122,37,0.18)',
        }}>谢谢</div>
        <div style={{ flex: 1, paddingTop: 60 }}>
          <div style={{ fontSize: 13, fontWeight: 600, letterSpacing: '0.22em', textTransform: 'uppercase', color: ember, marginBottom: 18 }}>
            xiè · xie / thank you
          </div>
          <div style={{ fontFamily: 'Fraunces, serif', fontSize: 64, lineHeight: 1.05, letterSpacing: -1.4, fontWeight: 400 }}>
            The AI grandchild that protects, remembers, and never sleeps.
          </div>
        </div>
      </div>

      {/* bottom credits */}
      <div style={{ position: 'absolute', bottom: 56, left: 80, right: 80, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', fontSize: 15, color: muted }}>
        <div style={{ display: 'flex', gap: 36 }}>
          <Field label="Brain" value="GLM-5.1, on-device" />
          <Field label="Memory" value="Plain markdown wiki" />
          <Field label="Voice" value="Local STT + TTS" />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span>For Margaret, 74</span>
          <span style={{ width: 4, height: 4, borderRadius: '50%', background: muted }} />
          <span>And every grandparent</span>
        </div>
      </div>
    </div>
  );
}

function Field({ label, value }) {
  return (
    <div>
      <div style={{ fontSize: 11, letterSpacing: '0.16em', textTransform: 'uppercase', opacity: 0.55, marginBottom: 4 }}>{label}</div>
      <div style={{ color: ink, fontWeight: 500 }}>{value}</div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// Cover C · Letter from a grandchild
// Looks like a handwritten note on cream paper, 谢谢 as the seal.
// ─────────────────────────────────────────────────────────────
function CoverLetter() {
  return (
    <div style={{
      width: COVER_W, height: COVER_H, position: 'relative', overflow: 'hidden',
      background: '#2a1f14', fontFamily: 'Inter, sans-serif',
    }}>
      {/* desk shadow */}
      <div style={{ position: 'absolute', inset: 0, background: 'radial-gradient(ellipse at center, rgba(0,0,0,0) 30%, rgba(0,0,0,0.4) 100%)' }} />

      {/* paper */}
      <div style={{
        position: 'absolute', left: 96, top: 56, bottom: 56, right: 96,
        background: '#f6efe1',
        boxShadow: '0 30px 80px rgba(0,0,0,0.5), 0 0 0 1px rgba(0,0,0,0.04)',
        transform: 'rotate(-0.6deg)',
        padding: '72px 88px',
        display: 'flex', flexDirection: 'column', color: ink,
      }}>
        {/* margin rule */}
        <div style={{ position: 'absolute', left: 64, top: 48, bottom: 48, width: 1, background: 'rgba(184,53,28,0.3)' }} />

        {/* date line */}
        <div style={{ alignSelf: 'flex-end', fontFamily: 'Fraunces, serif', fontStyle: 'italic', fontSize: 18, color: muted, marginBottom: 28 }}>
          Palo Alto · May 2026
        </div>

        <div style={{ fontFamily: 'Fraunces, serif', fontSize: 30, fontStyle: 'italic', color: muted, marginBottom: 20 }}>
          Dear Grandma,
        </div>

        <div style={{
          fontFamily: 'Fraunces, serif', fontSize: 56, lineHeight: 1.15, letterSpacing: -0.8,
          fontWeight: 400, maxWidth: 880,
        }}>
          I made you something that watches the bad emails so you don't have to.
          It listens when you ask, and it tells me only if it must.
        </div>

        <div style={{ flex: 1 }} />

        {/* signature row */}
        <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 32 }}>
          <div>
            <div style={{ fontFamily: 'Fraunces, serif', fontStyle: 'italic', fontSize: 22, color: muted, marginBottom: 6 }}>
              Yours,
            </div>
            <div style={{ fontFamily: 'Fraunces, serif', fontSize: 44, fontWeight: 500, letterSpacing: -0.4 }}>
              Xiexie
            </div>
            <div style={{ fontSize: 14, color: muted, marginTop: 8, letterSpacing: '0.12em', textTransform: 'uppercase' }}>
              The AI grandchild
            </div>
          </div>

          {/* wax seal */}
          <div style={{
            width: 132, height: 132, borderRadius: '50%',
            background: 'radial-gradient(circle at 35% 30%, #d97a25 0%, #a64f10 60%, #6e3208 100%)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: '#fff3d6', fontFamily: '"Noto Serif SC", "Songti SC", serif',
            fontSize: 56, fontWeight: 500, letterSpacing: -2,
            boxShadow: 'inset 0 4px 12px rgba(255,200,140,0.4), inset 0 -6px 14px rgba(0,0,0,0.3), 0 8px 20px rgba(0,0,0,0.25)',
            transform: 'rotate(-6deg)',
          }}>
            谢谢
          </div>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { CoverHearth, CoverBilingual, CoverLetter });
