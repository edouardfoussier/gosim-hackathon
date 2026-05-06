//
//  WarningGlyphView.swift
//  leanring-buddy
//
//  Side-screen warning-glyph overlay content. Renders a large, senior-friendly
//  status badge — phishing triangle, suspicious circle, or clear checkmark —
//  with a short label below it. The overlay window itself (NSPanel + click-
//  through behavior) lives in WarningGlyphOverlay.swift.
//
//  The base glyph geometry is ported from the SVG references in
//  /Users/edouardfoussier/Downloads/Xiexie-design/glyphs.jsx — same 0..48
//  coordinate space, same path commands, just expressed via SwiftUI Path
//  so we get crisp Retina-scale rendering for free.
//

import SwiftUI

// MARK: - Severity

/// The three verdict severities the side-screen overlay can display.
/// Each severity carries its own glyph shape, color, label, animation
/// style, and on-screen duration.
enum WarningGlyphSeverity: String, Equatable {
    case phishing
    case suspicious
    case clear

    /// Primary fill color for the glyph shape.
    var glyphFillColor: Color {
        switch self {
        case .phishing: return Color(red: 0xE5 / 255, green: 0x48 / 255, blue: 0x4D / 255)
        case .suspicious: return Color(red: 0xF5 / 255, green: 0xA5 / 255, blue: 0x24 / 255)
        case .clear: return Color(red: 0x4E / 255, green: 0xCB / 255, blue: 0x71 / 255)
        }
    }

    /// Senior-readable label rendered under the glyph.
    var labelText: String {
        switch self {
        case .phishing: return "This is a scam."
        case .suspicious: return "Something looks off."
        case .clear: return "This one is real."
        }
    }

    /// Total seconds the panel stays on screen (including fade-in/fade-out
    /// padding). Phishing and suspicious linger so a senior across the room
    /// can register the warning; clear is a brief reassurance.
    var totalOnScreenDurationSeconds: Double {
        switch self {
        case .phishing: return 6.0
        case .suspicious: return 5.5
        case .clear: return 3.0
        }
    }
}

// MARK: - Phishing glyph geometry

/// Rounded triangle outline ported from glyphs.jsx:
///   d="M24 5.4 L43 39.6 Q44.2 41.7 41.8 41.7 L6.2 41.7 Q3.8 41.7 5 39.6 Z"
/// Drawn in the source 0..48 coordinate space and uniformly scaled to fit
/// the supplied rect. Always centered if the rect isn't square.
struct PhishingTriangleShape: Shape {
    func path(in rect: CGRect) -> Path {
        let scaleFactor = min(rect.width, rect.height) / 48.0
        let horizontalCenteringOffset = (rect.width - 48 * scaleFactor) / 2.0 + rect.minX
        let verticalCenteringOffset = (rect.height - 48 * scaleFactor) / 2.0 + rect.minY

        func sourceToScaledPoint(_ sourceX: CGFloat, _ sourceY: CGFloat) -> CGPoint {
            return CGPoint(
                x: sourceX * scaleFactor + horizontalCenteringOffset,
                y: sourceY * scaleFactor + verticalCenteringOffset
            )
        }

        var path = Path()
        path.move(to: sourceToScaledPoint(24, 5.4))
        path.addLine(to: sourceToScaledPoint(43, 39.6))
        path.addQuadCurve(to: sourceToScaledPoint(41.8, 41.7), control: sourceToScaledPoint(44.2, 41.7))
        path.addLine(to: sourceToScaledPoint(6.2, 41.7))
        path.addQuadCurve(to: sourceToScaledPoint(5, 39.6), control: sourceToScaledPoint(3.8, 41.7))
        path.closeSubpath()
        return path
    }
}

/// White exclamation mark (bar + dot) drawn in the same 0..48 source space
/// as the triangle so the two shapes line up perfectly when stacked in a
/// ZStack with identical frames.
struct PhishingExclamationShape: Shape {
    func path(in rect: CGRect) -> Path {
        let scaleFactor = min(rect.width, rect.height) / 48.0
        let horizontalCenteringOffset = (rect.width - 48 * scaleFactor) / 2.0 + rect.minX
        let verticalCenteringOffset = (rect.height - 48 * scaleFactor) / 2.0 + rect.minY

        var path = Path()

        // Vertical bar: rect x=22.5 y=17 w=3 h=13 rx=1.5
        let barRect = CGRect(
            x: 22.5 * scaleFactor + horizontalCenteringOffset,
            y: 17.0 * scaleFactor + verticalCenteringOffset,
            width: 3.0 * scaleFactor,
            height: 13.0 * scaleFactor
        )
        path.addRoundedRect(
            in: barRect,
            cornerSize: CGSize(width: 1.5 * scaleFactor, height: 1.5 * scaleFactor)
        )

        // Dot: circle cx=24 cy=34 r=1.8
        let dotDiameter = 3.6 * scaleFactor
        let dotRect = CGRect(
            x: (24.0 - 1.8) * scaleFactor + horizontalCenteringOffset,
            y: (34.0 - 1.8) * scaleFactor + verticalCenteringOffset,
            width: dotDiameter,
            height: dotDiameter
        )
        path.addEllipse(in: dotRect)

        return path
    }
}

// MARK: - Clear (safe) checkmark geometry

/// White checkmark stroke ported from glyphs.jsx:
///   d="M14 24.5 L21 31.5 L34 17.5"
/// Rendered as an open path so SwiftUI strokes it with a rounded line cap.
struct ClearCheckmarkShape: Shape {
    func path(in rect: CGRect) -> Path {
        let scaleFactor = min(rect.width, rect.height) / 48.0
        let horizontalCenteringOffset = (rect.width - 48 * scaleFactor) / 2.0 + rect.minX
        let verticalCenteringOffset = (rect.height - 48 * scaleFactor) / 2.0 + rect.minY

        func sourceToScaledPoint(_ sourceX: CGFloat, _ sourceY: CGFloat) -> CGPoint {
            return CGPoint(
                x: sourceX * scaleFactor + horizontalCenteringOffset,
                y: sourceY * scaleFactor + verticalCenteringOffset
            )
        }

        var path = Path()
        path.move(to: sourceToScaledPoint(14, 24.5))
        path.addLine(to: sourceToScaledPoint(21, 31.5))
        path.addLine(to: sourceToScaledPoint(34, 17.5))
        return path
    }
}

// MARK: - Glyph view

/// The entire side-screen warning panel — translucent rounded card containing
/// a large pulsing/bobbing/static glyph and a senior-scale label.
///
/// The view is intentionally self-contained: animation drivers are toggled on
/// `.onAppear`, fade-in/fade-out is handled via a published `panelOpacity`
/// supplied by the manager, and the parent `NSPanel` does the slide-in
/// translation by animating its frame origin.
struct WarningGlyphView: View {
    let severity: WarningGlyphSeverity
    /// 0..1 opacity controlled by the manager — drives the cross-fade when
    /// a new verdict arrives mid-display, and the final fade-out before the
    /// panel is hidden.
    let panelOpacity: Double

    /// Drives the phishing pulse: scale 1.0 → 1.06, glow 0.45 → 0.85.
    @State private var pulseAnimationProgress: CGFloat = 0.0
    /// Drives the suspicious bob: vertical translation 0 → -6 pt and back.
    @State private var bobAnimationOffsetY: CGFloat = 0.0

    var body: some View {
        VStack(spacing: 20) {
            glyphView
                .frame(width: 132, height: 132)
                // Phishing pulse — scale + glow drive a 1.4s breathing rhythm
                // so the eye is drawn even when the user is looking elsewhere.
                .scaleEffect(severity == .phishing ? (1.0 + 0.06 * pulseAnimationProgress) : 1.0)
                .shadow(
                    color: severity == .phishing
                        ? severity.glyphFillColor.opacity(Double(0.45 + 0.4 * pulseAnimationProgress))
                        : .clear,
                    radius: severity == .phishing ? (8.0 + 14.0 * pulseAnimationProgress) : 0
                )
                // Suspicious bob — gentle vertical drift, ±6 pt over 2s.
                .offset(y: severity == .suspicious ? bobAnimationOffsetY : 0)

            Text(severity.labelText)
                // 26pt is the senior-typography sweet spot — readable from
                // a couch ~3m away on a Retina display without being so big
                // that it crowds the 280pt-wide panel.
                .font(.system(size: 26, weight: .semibold, design: .rounded))
                .foregroundColor(.white)
                .multilineTextAlignment(.center)
                .lineLimit(2)
                .minimumScaleFactor(0.85)
                .padding(.horizontal, 12)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(.vertical, 36)
        .padding(.horizontal, 20)
        .background(
            RoundedRectangle(cornerRadius: 28, style: .continuous)
                .fill(Color.black.opacity(0.78))
                .overlay(
                    RoundedRectangle(cornerRadius: 28, style: .continuous)
                        .strokeBorder(severity.glyphFillColor.opacity(0.55), lineWidth: 2)
                )
                .shadow(color: Color.black.opacity(0.45), radius: 24, x: 0, y: 8)
        )
        .opacity(panelOpacity)
        .onAppear {
            startSeverityDrivenAnimations()
        }
    }

    // MARK: - Glyph rendering per severity

    @ViewBuilder
    private var glyphView: some View {
        switch severity {
        case .phishing:
            ZStack {
                PhishingTriangleShape()
                    .fill(severity.glyphFillColor)
                PhishingExclamationShape()
                    .fill(Color(red: 0xFF / 255, green: 0xF8 / 255, blue: 0xEB / 255))
            }
        case .suspicious:
            ZStack {
                Circle()
                    .fill(severity.glyphFillColor)
                Text("?")
                    .font(.system(size: 78, weight: .bold, design: .rounded))
                    .foregroundColor(Color(red: 0xFF / 255, green: 0xF8 / 255, blue: 0xEB / 255))
                    .offset(y: -2)
            }
        case .clear:
            ZStack {
                Circle()
                    .fill(severity.glyphFillColor)
                ClearCheckmarkShape()
                    .stroke(
                        Color(red: 0xF1 / 255, green: 0xF7 / 255, blue: 0xEC / 255),
                        style: StrokeStyle(lineWidth: 9.5, lineCap: .round, lineJoin: .round)
                    )
            }
        }
    }

    // MARK: - Animation drivers

    /// Kicks off the per-severity ambient animation when the view appears.
    /// Each animation is a `repeatForever` loop driven by a single `@State`
    /// progress value so SwiftUI can interpolate scale, shadow radius, and
    /// translation without piling on extra timers.
    private func startSeverityDrivenAnimations() {
        switch severity {
        case .phishing:
            // 1.4s on/off pulse — explicit easeInOut so the apex (when the
            // glyph is at peak scale + brightest glow) feels like a heartbeat.
            withAnimation(.easeInOut(duration: 1.4).repeatForever(autoreverses: true)) {
                pulseAnimationProgress = 1.0
            }
        case .suspicious:
            // 2s vertical bob — translates ±6pt so the circle drifts gently
            // without becoming distracting. Eased so it dwells at the extremes.
            withAnimation(.easeInOut(duration: 2.0).repeatForever(autoreverses: true)) {
                bobAnimationOffsetY = -6.0
            }
        case .clear:
            // Clear stays static — it's a reassurance badge, not a peripheral
            // vision alert. Showing motion here would imply ongoing concern.
            break
        }
    }
}
