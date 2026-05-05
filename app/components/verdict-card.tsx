"use client";

import type { CSSProperties, ReactNode } from "react";
import clsx from "clsx";

// Ported from `Xiexie_claudedesign/verdict.jsx` — three variants
// (phishing / suspicious / clear) on a 760×980 floating cream card.
// The dynamic per-variant gradients and accent colours stay in inline
// `style` because Tailwind's JIT can't pre-compile arbitrary values
// from runtime data; the static cream + ink tones use Tailwind
// arbitrary classes so the design stays pixel-true.

const FRAUNCES = "var(--font-fraunces), Fraunces, ui-serif, Georgia, serif";
const INTER = "var(--font-inter), Inter, ui-sans-serif, system-ui, sans-serif";

type Variant = "phishing" | "suspicious" | "clear";
type Confidence = "high" | "medium" | "low";

export type VerdictSign = {
  tactic?: string;
  text: ReactNode;
};

export type VerdictCardProps = {
  variant: Variant;
  confidence?: Confidence;
  signs?: VerdictSign[];
  speakAloud?: string;
  onTellFamily?: () => void;
  onArchive?: () => void;
  onShowDetails?: () => void;
  scale?: number;
};

type Tone = {
  name: string;
  defaultHeadline: string;
  defaultSubhead: string | null;
  bannerBg: string;
  bannerInk: string;
  accent: string;
  accentSoft: string;
  accentLine: string;
  glyph: string;
  shadow: string;
};

const TONES: Record<Variant, Tone> = {
  phishing: {
    name: "Phishing",
    defaultHeadline: "I don't think this is really from your bank.",
    defaultSubhead:
      "Don't click anything in this email. Don't reply. I'll help.",
    bannerBg:
      "linear-gradient(135deg, #d44a2a 0%, #b8351c 60%, #8a2412 100%)",
    bannerInk: "#fff5ec",
    accent: "#b8351c",
    accentSoft: "rgba(184,53,28,0.10)",
    accentLine: "rgba(184,53,28,0.22)",
    glyph: "!",
    shadow:
      "0 30px 80px rgba(122,60,28,0.18), 0 6px 20px rgba(122,60,28,0.10), 0 0 0 1px rgba(31,26,20,0.04)",
  },
  suspicious: {
    name: "Suspicious",
    defaultHeadline: "Something here looks a little off.",
    defaultSubhead:
      "It might be fine, but I'd ask before opening any links.",
    bannerBg:
      "linear-gradient(135deg, #e9a259 0%, #d97a25 60%, #a55a18 100%)",
    bannerInk: "#fff8eb",
    accent: "#a55a18",
    accentSoft: "rgba(217,122,37,0.10)",
    accentLine: "rgba(217,122,37,0.22)",
    glyph: "?",
    shadow:
      "0 30px 80px rgba(122,60,28,0.18), 0 6px 20px rgba(122,60,28,0.10), 0 0 0 1px rgba(31,26,20,0.04)",
  },
  clear: {
    name: "Safe",
    defaultHeadline: "This looks fine to me.",
    defaultSubhead: null,
    bannerBg:
      "linear-gradient(135deg, #4a8a55 0%, #2f6d3f 60%, #1f4a2a 100%)",
    bannerInk: "#f1f7ec",
    accent: "#2f6d3f",
    accentSoft: "rgba(47,109,63,0.10)",
    accentLine: "rgba(47,109,63,0.22)",
    glyph: "✓",
    shadow:
      "0 30px 80px rgba(47,109,63,0.14), 0 6px 20px rgba(47,109,63,0.08), 0 0 0 1px rgba(31,26,20,0.04)",
  },
};

const TACTIC_LABEL: Record<string, string> = {
  authority: "authority",
  urgency: "urgency",
  social_proof: "social proof",
  scarcity: "scarcity",
  reciprocity: "reciprocity",
  liking: "liking",
  commitment: "commitment",
};

const CONFIDENCE_LABEL: Record<Confidence, string> = {
  high: "high confidence",
  medium: "medium confidence",
  low: "low confidence",
};

export function VerdictCard({
  variant,
  confidence,
  signs,
  speakAloud,
  onTellFamily,
  onArchive,
  onShowDetails,
  scale = 1,
}: VerdictCardProps) {
  const tone = TONES[variant];

  const wrapperStyle: CSSProperties =
    scale !== 1
      ? {
          width: 760 * scale,
          height: 980 * scale,
        }
      : {};

  const cardStyle: CSSProperties = {
    width: 760,
    height: 980,
    boxShadow: tone.shadow,
    fontFamily: INTER,
    fontSize: 18,
    transform: scale !== 1 ? `scale(${scale})` : undefined,
    transformOrigin: "top left",
  };

  const card =
    variant === "clear" ? (
      <ClearCard
        tone={tone}
        speakAloud={speakAloud}
        onShowDetails={onShowDetails}
        cardStyle={cardStyle}
      />
    ) : (
      <AlertCard
        variant={variant}
        tone={tone}
        confidence={confidence}
        signs={signs ?? []}
        speakAloud={speakAloud}
        onTellFamily={onTellFamily}
        onArchive={onArchive}
        onShowDetails={onShowDetails}
        cardStyle={cardStyle}
      />
    );

  // Outer wrapper reserves the post-scale footprint so the card doesn't
  // overflow its parent when scaled down for inline previews.
  if (scale !== 1) {
    return (
      <div style={wrapperStyle} className="relative">
        {card}
      </div>
    );
  }
  return card;
}

type AlertCardProps = {
  variant: Exclude<Variant, "clear">;
  tone: Tone;
  confidence?: Confidence;
  signs: VerdictSign[];
  speakAloud?: string;
  onTellFamily?: () => void;
  onArchive?: () => void;
  onShowDetails?: () => void;
  cardStyle: CSSProperties;
};

function AlertCard({
  variant,
  tone,
  confidence,
  signs,
  speakAloud,
  onTellFamily,
  onArchive,
  onShowDetails,
  cardStyle,
}: AlertCardProps) {
  const headline = speakAloud?.trim() || tone.defaultHeadline;
  const subhead = speakAloud?.trim() ? null : tone.defaultSubhead;
  const chip = confidence ? CONFIDENCE_LABEL[confidence] : null;

  // Action ordering follows the source design: phishing leads with
  // "Tell Lisa", suspicious leads with "Archive".
  const primary =
    variant === "phishing"
      ? {
          label: "Tell Lisa about this",
          onClick: onTellFamily,
        }
      : {
          label: "Archive it for me",
          onClick: onArchive,
        };
  const secondary =
    variant === "phishing"
      ? {
          label: "Archive it for me",
          onClick: onArchive,
        }
      : {
          label: "Tell Lisa about this",
          onClick: onTellFamily,
        };
  const tertiary = {
    label: "Show me the technical details",
    onClick: onShowDetails,
  };

  return (
    <div
      className="flex flex-col overflow-hidden rounded-[28px] bg-[#fbf7f0] text-[#1f1a14]"
      style={cardStyle}
    >
      <Banner tone={tone} chip={chip} headline={headline} subhead={subhead} />

      <div className="flex flex-1 flex-col gap-4 px-11 pb-4 pt-8">
        <div
          className="mb-1 font-semibold uppercase text-[#1f1a14]/40"
          style={{ fontSize: 13, letterSpacing: "0.18em" }}
        >
          Why I think so
        </div>
        {signs.length === 0 ? (
          <EmptySigns tone={tone} />
        ) : (
          signs.map((sign, i) => (
            <SignCard key={i} sign={sign} tone={tone} index={i + 1} />
          ))
        )}
      </div>

      <div className="flex flex-col gap-2.5 px-11 pb-9 pt-2">
        <ActionButton
          label={primary.label}
          kind="primary"
          tone={tone}
          onClick={primary.onClick}
        />
        <ActionButton
          label={secondary.label}
          kind="secondary"
          tone={tone}
          onClick={secondary.onClick}
        />
        <ActionButton
          label={tertiary.label}
          kind="ghost"
          tone={tone}
          onClick={tertiary.onClick}
        />
      </div>
    </div>
  );
}

type ClearCardProps = {
  tone: Tone;
  speakAloud?: string;
  onShowDetails?: () => void;
  cardStyle: CSSProperties;
};

function ClearCard({
  tone,
  speakAloud,
  onShowDetails,
  cardStyle,
}: ClearCardProps) {
  const headline = speakAloud?.trim() || tone.defaultHeadline;
  const body =
    "The sender, the links, and the signing checks all match what I'd expect. You can read it without worrying.";

  return (
    <div
      className="flex flex-col justify-between overflow-hidden rounded-[28px] bg-[#fbf7f0] text-[#1f1a14]"
      style={cardStyle}
    >
      <Banner tone={tone} chip={null} headline={headline} subhead={null} />

      <div className="flex flex-1 flex-col justify-center gap-6 px-11 py-10">
        <div
          className="text-[#1f1a14]/60"
          style={{
            fontSize: 22,
            lineHeight: 1.5,
            textWrap: "pretty",
          }}
        >
          {body}
        </div>

        <div
          className="flex items-center gap-3.5 rounded-2xl px-5 py-4"
          style={{
            background: tone.accentSoft,
            border: `0.5px solid ${tone.accentLine}`,
          }}
        >
          <div
            className="h-2.5 w-2.5 rounded-full"
            style={{
              background: tone.accent,
              boxShadow: `0 0 0 4px ${tone.accentSoft}`,
            }}
          />
          <div className="text-[#1f1a14]" style={{ fontSize: 17 }}>
            From <strong className="font-semibold">Lisa Chen</strong> · Domain
            check passed · Signing valid
          </div>
        </div>
      </div>

      <div className="px-11 pb-9">
        <ActionButton
          label="Show me why"
          kind="ghost"
          tone={tone}
          onClick={onShowDetails}
        />
      </div>
    </div>
  );
}

type BannerProps = {
  tone: Tone;
  chip: string | null;
  headline: string;
  subhead: string | null;
};

function Banner({ tone, chip, headline, subhead }: BannerProps) {
  return (
    <div
      className="relative overflow-hidden"
      style={{
        background: tone.bannerBg,
        color: tone.bannerInk,
        padding: "36px 44px 38px",
      }}
    >
      {/* Soft glow in the top-right corner of the banner. */}
      <div
        className="pointer-events-none absolute"
        style={{
          right: -120,
          top: -120,
          width: 380,
          height: 380,
          borderRadius: "50%",
          background:
            "radial-gradient(circle, rgba(255,255,255,0.18), transparent 65%)",
        }}
      />

      <div className="relative flex items-center justify-between">
        <div
          className="font-medium uppercase"
          style={{
            fontSize: 13,
            letterSpacing: "0.18em",
            opacity: 0.85,
          }}
        >
          Xiexie has read this email
        </div>
        {chip && (
          <div
            className="rounded-full"
            style={{
              fontSize: 13,
              padding: "6px 14px",
              background: "rgba(0,0,0,0.18)",
              backdropFilter: "blur(8px)",
              color: tone.bannerInk,
              letterSpacing: "0.04em",
              border: "0.5px solid rgba(255,255,255,0.18)",
            }}
          >
            {chip}
          </div>
        )}
      </div>

      <div className="relative mt-6 flex items-start gap-[22px]">
        <BannerGlyph char={tone.glyph} />
        <div className="min-w-0 flex-1">
          <div
            style={{
              fontFamily: FRAUNCES,
              fontSize: 32,
              fontWeight: 500,
              letterSpacing: -0.6,
              lineHeight: 1.05,
              color: tone.bannerInk,
              opacity: 0.9,
              marginBottom: 4,
            }}
          >
            {tone.name}
          </div>
          <div
            style={{
              fontFamily: FRAUNCES,
              fontSize: 38,
              lineHeight: 1.18,
              fontWeight: 400,
              letterSpacing: -0.4,
              textWrap: "pretty",
            }}
          >
            {headline}
          </div>
          {subhead && (
            <div
              style={{
                marginTop: 14,
                fontSize: 19,
                lineHeight: 1.5,
                opacity: 0.92,
              }}
            >
              {subhead}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function BannerGlyph({ char }: { char: string }) {
  return (
    <div
      className="flex shrink-0 items-center justify-center"
      style={{
        width: 80,
        height: 80,
        borderRadius: 22,
        background: "rgba(0,0,0,0.18)",
        backdropFilter: "blur(8px)",
        border: "0.5px solid rgba(255,255,255,0.22)",
        fontFamily: FRAUNCES,
        fontSize: 50,
        fontWeight: 500,
        lineHeight: 1,
        color: "currentColor",
      }}
    >
      {char}
    </div>
  );
}

type SignCardProps = {
  sign: VerdictSign;
  tone: Tone;
  index: number;
};

function SignCard({ sign, tone, index }: SignCardProps) {
  const tacticLabel = sign.tactic ? TACTIC_LABEL[sign.tactic] ?? sign.tactic : null;
  return (
    <div
      className="relative flex gap-[18px] rounded-[20px] bg-white"
      style={{
        padding: "20px 24px",
        border: "0.5px solid rgba(31,26,20,0.06)",
        boxShadow:
          "0 1px 0 rgba(31,26,20,0.03), 0 8px 24px rgba(122,60,28,0.06)",
      }}
    >
      <div
        className="flex shrink-0 items-center justify-center"
        style={{
          width: 32,
          height: 32,
          borderRadius: 10,
          background: tone.accentSoft,
          color: tone.accent,
          fontFamily: FRAUNCES,
          fontSize: 18,
          fontWeight: 500,
        }}
      >
        {index}
      </div>
      <div
        className="min-w-0 flex-1 text-[#1f1a14]"
        style={{
          fontSize: 18,
          lineHeight: 1.5,
          paddingRight: tacticLabel ? 70 : 0,
          textWrap: "pretty",
        }}
      >
        {sign.text}
      </div>
      {tacticLabel && (
        <div
          className="absolute font-semibold uppercase"
          style={{
            top: 18,
            right: 22,
            fontSize: 11,
            padding: "4px 9px",
            borderRadius: 999,
            background: tone.accentSoft,
            color: tone.accent,
            letterSpacing: "0.12em",
            border: `0.5px solid ${tone.accentLine}`,
          }}
        >
          {tacticLabel}
        </div>
      )}
    </div>
  );
}

function EmptySigns({ tone }: { tone: Tone }) {
  // When the WS payload doesn't include structured signs (V1 default),
  // we render a quiet placeholder rather than an empty void so the
  // card silhouette stays balanced.
  return (
    <div
      className="rounded-[20px] bg-white text-[#1f1a14]/60"
      style={{
        padding: "20px 24px",
        border: "0.5px solid rgba(31,26,20,0.06)",
        boxShadow:
          "0 1px 0 rgba(31,26,20,0.03), 0 8px 24px rgba(122,60,28,0.06)",
        fontSize: 17,
        lineHeight: 1.5,
        background: tone.accentSoft,
      }}
    >
      I walked through the headers, the link the email points to, and what
      other people are reporting about this template. Tap{" "}
      <em className="not-italic font-semibold">Show me the technical details</em>{" "}
      if you want the full breakdown.
    </div>
  );
}

type ActionButtonProps = {
  label: string;
  kind: "primary" | "secondary" | "ghost";
  tone: Tone;
  onClick?: () => void;
};

function ActionButton({ label, kind, tone, onClick }: ActionButtonProps) {
  const interactive = typeof onClick === "function";
  const baseStyle: CSSProperties = {
    width: "100%",
    height: kind === "ghost" ? 48 : 56,
    borderRadius: 16,
    fontFamily: INTER,
    fontSize: kind === "ghost" ? 17 : 19,
    fontWeight: 500,
    letterSpacing: -0.1,
    padding: "0 20px",
    cursor: interactive ? "pointer" : "default",
  };

  if (kind === "primary") {
    return (
      <button
        type="button"
        onClick={onClick}
        disabled={!interactive}
        className={clsx(
          "flex items-center justify-center gap-2.5 transition-transform",
          interactive
            ? "hover:scale-[1.01] active:scale-[0.99]"
            : "cursor-default"
        )}
        style={{
          ...baseStyle,
          background: tone.accent,
          color: "#fff8eb",
          border: "none",
          boxShadow: `0 1px 0 rgba(255,255,255,0.2) inset, 0 6px 14px ${tone.accentSoft}, 0 0 0 1px ${tone.accent}`,
        }}
      >
        {label}
      </button>
    );
  }

  if (kind === "secondary") {
    return (
      <button
        type="button"
        onClick={onClick}
        disabled={!interactive}
        className={clsx(
          "flex items-center justify-center gap-2.5 bg-white text-[#1f1a14] transition-transform",
          interactive
            ? "hover:scale-[1.01] active:scale-[0.99]"
            : "cursor-default"
        )}
        style={{
          ...baseStyle,
          border: "0.5px solid rgba(31,26,20,0.16)",
          boxShadow: "0 1px 2px rgba(31,26,20,0.04)",
        }}
      >
        {label}
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={!interactive}
      className={clsx(
        "flex items-center justify-center gap-2.5 bg-transparent text-[#1f1a14]/60",
        interactive ? "hover:text-[#1f1a14]" : "cursor-default"
      )}
      style={{
        ...baseStyle,
        border: "none",
        textDecoration: "underline",
        textUnderlineOffset: 4,
        textDecorationColor: "rgba(31,26,20,0.25)",
      }}
    >
      {label}
    </button>
  );
}
