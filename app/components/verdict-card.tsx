"use client";

import type { CSSProperties, ReactNode } from "react";
import { Archive, Info, Send, ShieldCheck } from "lucide-react";
import clsx from "clsx";
import {
  UrlSandboxPreview,
  type UrlSandboxData,
} from "./url-sandbox-preview";

export type { UrlSandboxData };

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
  urlSandbox?: UrlSandboxData;
  familyContact?: string;
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
  fear: "fear",
};

// Per-Cialdini-family palette. Stays inside the cream/ember world plus the
// existing phishing/suspicious deep reds. Each entry maps to:
//   `bg`      — chip background (translucent of `ink`)
//   `border`  — hairline (slightly stronger translucent of `ink`)
//   `ink`     — chip text color
//   `tooltip` — sentence shown on hover (also exposed via `title`).
type TacticStyle = {
  bg: string;
  border: string;
  ink: string;
  tooltip: string;
};

const TACTIC_STYLE: Record<string, TacticStyle> = {
  // urgency / scarcity → red-orange
  urgency: {
    bg: "rgba(212,74,42,0.12)",
    border: "rgba(212,74,42,0.26)",
    ink: "#a8331b",
    tooltip:
      "This message is rushing you to act fast — that's a classic scam tactic.",
  },
  scarcity: {
    bg: "rgba(212,74,42,0.12)",
    border: "rgba(212,74,42,0.26)",
    ink: "#a8331b",
    tooltip:
      "It's pretending only a few people get this, so you don't pause to think.",
  },
  // authority / fear → deep red
  authority: {
    bg: "rgba(138,36,18,0.12)",
    border: "rgba(138,36,18,0.26)",
    ink: "#7a1f10",
    tooltip:
      "It's leaning on a trusted name (a bank, the IRS, a doctor) so you don't question it.",
  },
  fear: {
    bg: "rgba(138,36,18,0.12)",
    border: "rgba(138,36,18,0.26)",
    ink: "#7a1f10",
    tooltip:
      "It's frightening you — that's a tactic to make you click before thinking.",
  },
  // liking / reciprocity → amber
  liking: {
    bg: "rgba(217,122,37,0.14)",
    border: "rgba(217,122,37,0.28)",
    ink: "#9b461c",
    tooltip:
      "It's being warm or familiar to gain your trust — be careful.",
  },
  reciprocity: {
    bg: "rgba(217,122,37,0.14)",
    border: "rgba(217,122,37,0.28)",
    ink: "#9b461c",
    tooltip:
      "It's offering you something so you feel obliged to give back — be careful.",
  },
  // social-proof / commitment → soft taupe
  social_proof: {
    bg: "rgba(94,44,25,0.10)",
    border: "rgba(94,44,25,0.22)",
    ink: "#5e2c19",
    tooltip:
      "It says 'everyone is doing this' so you don't want to be the odd one out.",
  },
  commitment: {
    bg: "rgba(94,44,25,0.10)",
    border: "rgba(94,44,25,0.22)",
    ink: "#5e2c19",
    tooltip:
      "It's reminding you of something you said before so you stay consistent — be careful.",
  },
};

// Fallback for tactics outside the known set: use the variant tone.
function tacticStyleFor(tactic: string, tone: Tone): TacticStyle {
  return (
    TACTIC_STYLE[tactic] ?? {
      bg: tone.accentSoft,
      border: tone.accentLine,
      ink: tone.accent,
      tooltip:
        "Xiexie spotted a persuasion tactic in this message — go slow.",
    }
  );
}

function confidenceLabel(
  variant: Variant,
  confidence: Confidence | undefined
): string | null {
  if (!confidence) return null;
  if (variant === "clear" && confidence === "high") return "I'm sure";
  if (variant === "phishing" && confidence === "high") return "Very confident";
  if (confidence === "high") return "high confidence";
  if (confidence === "medium") return "medium confidence";
  return "low confidence";
}

export function VerdictCard({
  variant,
  confidence,
  signs,
  speakAloud,
  urlSandbox,
  familyContact,
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
        confidence={confidence}
        speakAloud={speakAloud}
        familyContact={familyContact}
        onTellFamily={onTellFamily}
        onArchive={onArchive}
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
        urlSandbox={urlSandbox}
        familyContact={familyContact}
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
  urlSandbox?: UrlSandboxData;
  familyContact?: string;
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
  urlSandbox,
  familyContact,
  onTellFamily,
  onArchive,
  onShowDetails,
  cardStyle,
}: AlertCardProps) {
  const headline = speakAloud?.trim() || tone.defaultHeadline;
  const subhead = speakAloud?.trim() ? null : tone.defaultSubhead;
  const ribbon = confidenceLabel(variant, confidence);
  const familyName = familyContact?.trim() || "Lisa";
  const tellFamilyLabel = `Tell ${familyName}`;

  // Action ordering follows the source design: phishing leads with
  // "Tell {family}", suspicious leads with "Archive".
  const tellAction = {
    label: tellFamilyLabel,
    onClick: onTellFamily,
    icon: <Send size={20} aria-hidden="true" />,
  };
  const archiveAction = {
    label: "Archive it for me",
    onClick: onArchive,
    icon: <Archive size={20} aria-hidden="true" />,
  };
  const primary = variant === "phishing" ? tellAction : archiveAction;
  const secondary = variant === "phishing" ? archiveAction : tellAction;
  const tertiary = {
    label: "Show me the technical details",
    onClick: onShowDetails,
    icon: <Info size={18} aria-hidden="true" />,
  };

  return (
    <div
      className="flex flex-col overflow-hidden rounded-[28px] bg-[#fbf7f0] text-[#1f1a14]"
      style={cardStyle}
    >
      {/* Live region: lets screen readers + browser SpeechSynthesis pick
          up the verdict spoken line without us having to render it
          twice. Visible-hidden but assistive-tech-readable. */}
      {speakAloud && <SrLive text={speakAloud} />}

      <Banner
        tone={tone}
        ribbon={ribbon}
        ribbonStrong={
          variant === "phishing" && confidence === "high"
        }
        headline={headline}
        subhead={subhead}
      />

      <div className="flex flex-1 flex-col gap-4 px-11 pb-4 pt-7 overflow-hidden">
        <div
          className="font-semibold uppercase text-[#1f1a14]/40"
          style={{ fontSize: 13, letterSpacing: "0.18em" }}
        >
          Why I think so
        </div>
        {urlSandbox && (
          <UrlSandboxPreview tone={tone} data={urlSandbox} />
        )}
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
          icon={primary.icon}
          kind="primary"
          tone={tone}
          onClick={primary.onClick}
        />
        <ActionButton
          label={secondary.label}
          icon={secondary.icon}
          kind="secondary"
          tone={tone}
          onClick={secondary.onClick}
        />
        <ActionButton
          label={tertiary.label}
          icon={tertiary.icon}
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
  confidence?: Confidence;
  speakAloud?: string;
  familyContact?: string;
  onTellFamily?: () => void;
  onArchive?: () => void;
  onShowDetails?: () => void;
  cardStyle: CSSProperties;
};

function ClearCard({
  tone,
  confidence,
  speakAloud,
  familyContact,
  onTellFamily,
  onArchive,
  onShowDetails,
  cardStyle,
}: ClearCardProps) {
  const headline = speakAloud?.trim() || tone.defaultHeadline;
  const body =
    "The sender, the links, and the signing checks all match what I'd expect. You can read it without worrying.";
  const ribbon = confidenceLabel("clear", confidence);
  const familyName = familyContact?.trim() || "Lisa";
  // For safe emails we don't push CTAs on Margaret. We only render
  // them if the parent explicitly wired callbacks (e.g. "tell Lisa
  // this came through" for sentimental reasons).
  const showTellFamily = typeof onTellFamily === "function";
  const showArchive = typeof onArchive === "function";

  return (
    <div
      className="flex flex-col justify-between overflow-hidden rounded-[28px] bg-[#fbf7f0] text-[#1f1a14]"
      style={cardStyle}
    >
      {speakAloud && <SrLive text={speakAloud} />}
      <Banner
        tone={tone}
        ribbon={ribbon}
        ribbonStrong={confidence === "high"}
        headline={headline}
        subhead={null}
      />

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
          <div
            className="flex items-center gap-2 text-[#1f1a14]"
            style={{ fontSize: 17 }}
          >
            <ShieldCheck size={18} style={{ color: tone.accent }} aria-hidden />
            <span>
              From <strong className="font-semibold">Lisa Chen</strong> ·
              Domain check passed · Signing valid
            </span>
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-2.5 px-11 pb-9 pt-2">
        {showTellFamily && (
          <ActionButton
            label={`Tell ${familyName}`}
            icon={<Send size={20} aria-hidden="true" />}
            kind="secondary"
            tone={tone}
            onClick={onTellFamily}
          />
        )}
        {showArchive && (
          <ActionButton
            label="Archive it for me"
            icon={<Archive size={20} aria-hidden="true" />}
            kind="secondary"
            tone={tone}
            onClick={onArchive}
          />
        )}
        <ActionButton
          label="Show me why"
          icon={<Info size={18} aria-hidden="true" />}
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
  ribbon: string | null;
  ribbonStrong?: boolean;
  headline: string;
  subhead: string | null;
};

function Banner({ tone, ribbon, ribbonStrong, headline, subhead }: BannerProps) {
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
      </div>

      <div className="relative mt-6 flex items-start gap-[22px]">
        <BannerGlyph char={tone.glyph} />
        <div className="min-w-0 flex-1">
          <div
            className="flex items-center gap-3"
            style={{ marginBottom: 6 }}
          >
            <div
              style={{
                fontFamily: FRAUNCES,
                fontSize: 32,
                fontWeight: 500,
                letterSpacing: -0.6,
                lineHeight: 1.05,
                color: tone.bannerInk,
                opacity: 0.92,
              }}
            >
              {tone.name}
            </div>
            {ribbon && (
              <ConfidenceRibbon
                tone={tone}
                label={ribbon}
                strong={ribbonStrong}
              />
            )}
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

type ConfidenceRibbonProps = {
  tone: Tone;
  label: string;
  strong?: boolean;
};

function ConfidenceRibbon({ tone, label, strong }: ConfidenceRibbonProps) {
  return (
    <div
      className="inline-flex items-center gap-1.5 rounded-full"
      style={{
        fontSize: 12,
        padding: strong ? "5px 12px 5px 11px" : "4px 11px 4px 10px",
        background: strong ? "rgba(0,0,0,0.32)" : "rgba(0,0,0,0.18)",
        backdropFilter: "blur(8px)",
        color: tone.bannerInk,
        letterSpacing: "0.06em",
        textTransform: "uppercase",
        fontWeight: strong ? 600 : 500,
        border: `0.5px solid ${strong ? "rgba(255,255,255,0.32)" : "rgba(255,255,255,0.18)"}`,
        whiteSpace: "nowrap",
      }}
    >
      <span
        className="inline-block rounded-full"
        style={{
          width: strong ? 7 : 6,
          height: strong ? 7 : 6,
          background: tone.bannerInk,
          opacity: strong ? 0.95 : 0.7,
        }}
      />
      {label}
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
  const tactic = sign.tactic ?? null;
  const tacticLabel = tactic ? TACTIC_LABEL[tactic] ?? tactic : null;
  const tacticStyle = tactic ? tacticStyleFor(tactic, tone) : null;
  return (
    <div
      className="relative flex gap-[18px] rounded-[20px] bg-white"
      style={{
        padding: "18px 22px",
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
          fontSize: 17,
          lineHeight: 1.5,
          paddingRight: tacticLabel ? 88 : 0,
          textWrap: "pretty",
        }}
      >
        {sign.text}
      </div>
      {tacticLabel && tacticStyle && (
        <TacticChip
          label={tacticLabel}
          style={tacticStyle}
          floating
        />
      )}
    </div>
  );
}

type TacticChipProps = {
  label: string;
  style: TacticStyle;
  floating?: boolean;
};

function TacticChip({ label, style, floating }: TacticChipProps) {
  return (
    <div
      className={clsx(
        "font-semibold uppercase whitespace-nowrap",
        floating && "absolute"
      )}
      style={{
        ...(floating ? { top: 16, right: 18 } : {}),
        fontSize: 10,
        padding: "4px 9px",
        borderRadius: 999,
        background: style.bg,
        color: style.ink,
        letterSpacing: "0.14em",
        border: `0.5px solid ${style.border}`,
        cursor: "help",
      }}
      title={style.tooltip}
      aria-label={`${label} — ${style.tooltip}`}
    >
      {label}
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
  icon?: ReactNode;
};

function ActionButton({ label, kind, tone, onClick, icon }: ActionButtonProps) {
  const interactive = typeof onClick === "function";
  // 56px touch target for the two filled CTAs (above Apple HIG's 44px
  // floor) so Margaret's finger or trackpad doesn't have to fight us.
  // Ghost stays a hair shorter to keep the visual hierarchy obvious.
  const baseStyle: CSSProperties = {
    width: "100%",
    minHeight: kind === "ghost" ? 48 : 56,
    borderRadius: 16,
    fontFamily: INTER,
    fontSize: kind === "ghost" ? 17 : 19,
    fontWeight: 500,
    letterSpacing: -0.1,
    padding: "0 22px",
    cursor: interactive ? "pointer" : "default",
  };

  if (kind === "primary") {
    return (
      <button
        type="button"
        onClick={onClick}
        disabled={!interactive}
        className={clsx(
          "flex items-center justify-center gap-3 transition-transform",
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
        {icon && <span className="flex shrink-0 items-center">{icon}</span>}
        <span>{label}</span>
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
          "flex items-center justify-center gap-3 bg-white text-[#1f1a14] transition-transform",
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
        {icon && (
          <span
            className="flex shrink-0 items-center"
            style={{ color: tone.accent }}
          >
            {icon}
          </span>
        )}
        <span>{label}</span>
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={!interactive}
      className={clsx(
        "flex items-center justify-center gap-2 bg-transparent text-[#1f1a14]/60",
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
      {icon && (
        <span className="flex shrink-0 items-center opacity-70">{icon}</span>
      )}
      <span>{label}</span>
    </button>
  );
}

// Visually-hidden live region. Margaret's screen reader (VoiceOver on
// macOS) announces this on render; sighted users already see the
// headline. We keep the styles inline so we don't depend on a global
// `.sr-only` utility being present.
function SrLive({ text }: { text: string }) {
  return (
    <div
      aria-live="polite"
      role="status"
      style={{
        position: "absolute",
        width: 1,
        height: 1,
        padding: 0,
        margin: -1,
        overflow: "hidden",
        clip: "rect(0,0,0,0)",
        whiteSpace: "nowrap",
        border: 0,
      }}
    >
      {text}
    </div>
  );
}
