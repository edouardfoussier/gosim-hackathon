"use client";

import { ChevronDown } from "lucide-react";

// "What's behind the link" panel — extracted from VerdictCard so the
// parent stays under the line-count budget. Purely presentational; the
// data is pre-cooked by the backend (Playwright redirect capture +
// header forensics + scam-intel composition).

const MONO =
  "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, monospace";

export type UrlSandboxData = {
  visibleText: string;
  finalDomain: string;
  finalUrl?: string;
  redirectChain?: string[];
  domainAgeDays?: number;
  hostingNote?: string;
  screenshotUrl?: string;
};

// Minimal Tone shape — verdict-card.tsx owns the full type, but the
// sandbox panel only needs the four colour fields. Keeping the surface
// narrow lets the file be reused by any other warm/ember surface that
// wants to render a sandboxed-link preview.
export type UrlSandboxTone = {
  accent: string;
  accentSoft: string;
  accentLine: string;
};

type UrlSandboxPreviewProps = {
  tone: UrlSandboxTone;
  data: UrlSandboxData;
};

export function UrlSandboxPreview({ tone, data }: UrlSandboxPreviewProps) {
  const { visibleText, finalDomain, finalUrl, redirectChain, screenshotUrl } =
    data;
  // hostingNote takes precedence over domainAgeDays when both are present
  // so the backend can override the auto-generated tagline at will.
  const tagline =
    data.hostingNote?.trim() ||
    (typeof data.domainAgeDays === "number"
      ? `registered ${data.domainAgeDays} day${
          data.domainAgeDays === 1 ? "" : "s"
        } ago`
      : null);
  // Collapse the chain when there's only the final domain — that info
  // is already shown in the headline transformation row.
  const showChain =
    Array.isArray(redirectChain) && redirectChain.length >= 2;

  return (
    <div
      className="relative flex gap-4 rounded-[20px]"
      style={{
        padding: "16px 18px",
        background: "rgba(255,250,240,0.85)",
        border: `0.5px solid ${tone.accentLine}`,
        boxShadow:
          "0 1px 0 rgba(31,26,20,0.03), 0 8px 24px rgba(122,60,28,0.05)",
      }}
    >
      <div className="min-w-0 flex-1 flex flex-col gap-3">
        <div
          className="font-semibold uppercase flex items-center gap-2"
          style={{
            fontSize: 11,
            letterSpacing: "0.16em",
            color: tone.accent,
          }}
        >
          <span
            className="inline-block rounded-full"
            style={{
              width: 6,
              height: 6,
              background: tone.accent,
              boxShadow: `0 0 0 3px ${tone.accentSoft}`,
            }}
          />
          What&apos;s behind the link
        </div>

        <div className="flex flex-col gap-1.5">
          <div
            className="text-[#1f1a14]/70 italic"
            style={{ fontSize: 15, lineHeight: 1.4 }}
          >
            “{visibleText}”
          </div>
          <div
            className="flex items-center gap-2"
            style={{ color: tone.accent }}
          >
            <ChevronDown
              size={14}
              aria-hidden="true"
              style={{ flexShrink: 0 }}
            />
            <span
              className="font-semibold"
              style={{
                fontSize: 11,
                letterSpacing: "0.12em",
                textTransform: "uppercase",
                opacity: 0.75,
              }}
            >
              actually goes to
            </span>
          </div>
          <div
            className="break-all"
            style={{
              fontFamily: MONO,
              fontSize: 14,
              lineHeight: 1.4,
              color: "#1f1a14",
              fontWeight: 600,
            }}
            title={finalUrl ?? finalDomain}
          >
            {finalDomain}
          </div>
          {tagline && (
            <div
              className="text-[#1f1a14]/65"
              style={{ fontSize: 13, lineHeight: 1.4, marginTop: 2 }}
            >
              {tagline}
            </div>
          )}
        </div>

        {showChain && redirectChain && (
          <div
            className="flex flex-col gap-1 rounded-xl"
            style={{
              padding: "8px 10px",
              background: tone.accentSoft,
              border: `0.5px solid ${tone.accentLine}`,
            }}
          >
            <div
              className="font-semibold uppercase"
              style={{
                fontSize: 10,
                letterSpacing: "0.16em",
                color: tone.accent,
                opacity: 0.8,
              }}
            >
              Redirect hops
            </div>
            {redirectChain.map((hop, i) => (
              <div
                key={`${i}-${hop}`}
                className="flex items-baseline gap-2"
                style={{
                  fontFamily: MONO,
                  fontSize: 12,
                  lineHeight: 1.45,
                  color: "#2b1d12",
                }}
              >
                <span
                  style={{
                    color: tone.accent,
                    fontWeight: 600,
                    flexShrink: 0,
                    fontSize: 11,
                  }}
                >
                  {i + 1}.
                </span>
                <span className="break-all">{hop}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      <SandboxScreenshot tone={tone} src={screenshotUrl} />
    </div>
  );
}

function SandboxScreenshot({
  tone,
  src,
}: {
  tone: UrlSandboxTone;
  src?: string;
}) {
  const FRAME_W = 124;
  const FRAME_H = 156;
  return (
    <div
      className="shrink-0 overflow-hidden rounded-xl relative"
      style={{
        width: FRAME_W,
        height: FRAME_H,
        background: "rgba(251,247,240,0.9)",
        border: `0.5px dashed ${tone.accentLine}`,
        boxShadow: "inset 0 0 0 1px rgba(31,26,20,0.03)",
      }}
    >
      {src ? (
        // Edouard wires a real Playwright capture URL here for the demo.
        // Plain <img> by design — we don't optimize remote screenshots.
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={src}
          alt="Sandboxed preview of where the link leads"
          style={{
            width: "100%",
            height: "100%",
            objectFit: "cover",
            display: "block",
          }}
        />
      ) : (
        <div
          className="flex h-full w-full flex-col items-center justify-center text-center px-2"
          style={{
            color: tone.accent,
          }}
          aria-label="Sandboxed preview unavailable"
        >
          <div
            style={{
              fontSize: 22,
              lineHeight: 1,
              marginBottom: 8,
              opacity: 0.7,
            }}
          >
            🔍
          </div>
          <div
            className="uppercase font-semibold"
            style={{
              fontSize: 9,
              letterSpacing: "0.14em",
              opacity: 0.8,
              lineHeight: 1.3,
            }}
          >
            sandboxed preview
            <br />
            unavailable
          </div>
        </div>
      )}
    </div>
  );
}
