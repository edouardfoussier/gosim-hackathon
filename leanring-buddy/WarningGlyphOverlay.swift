//
//  WarningGlyphOverlay.swift
//  leanring-buddy
//
//  Side-screen warning-glyph overlay panel + manager. Mirrors the cursor
//  overlay pattern in OverlayWindow.swift but is right-anchored: a small
//  280×360 pt borderless transparent NSPanel docks in the top-right corner
//  of the primary screen, slides in from the right edge, displays a
//  WarningGlyphView, then auto-fades out after the severity's duration.
//
//  The panel is click-through (ignoresMouseEvents = true) and
//  non-activating, so it never steals focus from whatever Michel is
//  reading. Status-badge style — independent of where the cursor
//  companion is pointing.
//

import AppKit
import SwiftUI

// MARK: - Panel

/// Borderless, transparent, click-through NSPanel that hosts the
/// `WarningGlyphView`. Lives at `.screenSaver` level so it floats above
/// every regular app window, including full-screen apps.
final class WarningGlyphPanel: NSPanel {
    init(contentRect: NSRect) {
        super.init(
            contentRect: contentRect,
            // .nonactivatingPanel keeps focus on whatever app the user is
            // reading from when the glyph appears.
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: false
        )

        self.isOpaque = false
        self.backgroundColor = .clear
        self.hasShadow = false
        self.level = .screenSaver
        self.ignoresMouseEvents = true
        self.collectionBehavior = [.canJoinAllSpaces, .stationary, .fullScreenAuxiliary]
        self.isReleasedWhenClosed = false
        self.hidesOnDeactivate = false
        self.isMovableByWindowBackground = false
    }

    // The panel is purely decorative — never let it become key or main,
    // so it can never eat keyboard input or app focus.
    override var canBecomeKey: Bool { false }
    override var canBecomeMain: Bool { false }
}

// MARK: - SwiftUI host wrapper

/// Hostable wrapper that lets the manager mutate `severity` and
/// `panelOpacity` from outside SwiftUI without rebuilding the host view.
/// The manager nudges these via Combine, the view re-renders.
private final class WarningGlyphHostState: ObservableObject {
    @Published var currentSeverity: WarningGlyphSeverity = .phishing
    @Published var currentPanelOpacity: Double = 0.0
}

private struct WarningGlyphHostView: View {
    @ObservedObject var hostState: WarningGlyphHostState

    var body: some View {
        // Re-key on severity so SwiftUI restarts the .onAppear-driven
        // animations whenever the manager swaps verdicts mid-display.
        WarningGlyphView(
            severity: hostState.currentSeverity,
            panelOpacity: hostState.currentPanelOpacity
        )
        .id(hostState.currentSeverity)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

// MARK: - Manager

/// Owns the lifecycle of the side-screen warning-glyph panel. Public API
/// is a single `displayWarningGlyph(severity:)` call from
/// `CompanionManager` — the manager handles slide-in, hold, and fade-out
/// internally and is safe to call repeatedly (a new verdict mid-display
/// just cross-fades the existing panel).
@MainActor
final class WarningGlyphOverlayManager {

    // MARK: Layout constants

    /// Width of the side-screen panel. 280pt is wide enough for the 26pt
    /// "Something looks off." label without wrapping while still feeling
    /// peripheral rather than dominating the screen.
    private let panelWidth: CGFloat = 280
    private let panelHeight: CGFloat = 360
    /// Inset from the screen edges. Matches the ~24pt visual padding the
    /// macOS notification HUD uses, so the glyph sits in a familiar spot.
    private let panelEdgeInset: CGFloat = 24
    /// How far off-screen-right the panel starts before sliding in.
    private let slideInStartOffsetX: CGFloat = 320

    // MARK: Animation timing

    private let slideInDurationSeconds: TimeInterval = 0.45
    private let fadeInDurationSeconds: TimeInterval = 0.35
    private let fadeOutDurationSeconds: TimeInterval = 0.55

    // MARK: State

    private var panel: WarningGlyphPanel?
    private let hostState = WarningGlyphHostState()
    /// Background task that holds the panel on screen for the severity's
    /// duration, then fades out. Cancelled (and replaced) if a new
    /// verdict arrives while the existing panel is still visible.
    private var displayLifecycleTask: Task<Void, Never>?

    // MARK: Public API

    /// Show the warning-glyph panel for the given severity. If a panel is
    /// already on screen, swap its severity in place and restart the
    /// hold-and-fade timer instead of stacking a second window.
    func displayWarningGlyph(severity: WarningGlyphSeverity) {
        // Cancel any in-flight hold/fade so we don't race with the new verdict.
        displayLifecycleTask?.cancel()
        displayLifecycleTask = nil

        guard let primaryScreen = NSScreen.screens.first else {
            print("⚠️ WarningGlyphOverlayManager: no screen available to host panel")
            return
        }

        if panel == nil {
            buildAndPresentPanel(onScreen: primaryScreen, severity: severity)
        } else {
            // Reuse the existing panel — just swap the severity and make
            // sure the panel is positioned and fully visible. This is what
            // happens when, e.g., the user asks about a second email while
            // the first verdict is still on screen.
            hostState.currentSeverity = severity
            ensurePanelIsAtFinalPosition(onScreen: primaryScreen)
            ensurePanelIsFullyOpaque()
        }

        scheduleHoldAndFadeOut(forSeverity: severity)
    }

    /// Tear down the panel immediately (no fade). Called by `CompanionManager.stop`.
    func dismissImmediately() {
        displayLifecycleTask?.cancel()
        displayLifecycleTask = nil

        if let panel = panel {
            panel.orderOut(nil)
            panel.contentView = nil
            self.panel = nil
        }
        hostState.currentPanelOpacity = 0.0
    }

    // MARK: - Panel creation

    private func buildAndPresentPanel(onScreen primaryScreen: NSScreen, severity: WarningGlyphSeverity) {
        hostState.currentSeverity = severity
        hostState.currentPanelOpacity = 0.0

        let finalFrame = finalPanelFrame(onScreen: primaryScreen)
        let slideStartFrame = NSRect(
            x: finalFrame.origin.x + slideInStartOffsetX,
            y: finalFrame.origin.y,
            width: finalFrame.width,
            height: finalFrame.height
        )

        let newPanel = WarningGlyphPanel(contentRect: slideStartFrame)
        let hostingView = NSHostingView(rootView: WarningGlyphHostView(hostState: hostState))
        hostingView.frame = NSRect(origin: .zero, size: finalFrame.size)
        // The panel itself is fully opaque; SwiftUI's opacity drives the fade.
        newPanel.contentView = hostingView
        newPanel.alphaValue = 1.0

        newPanel.orderFrontRegardless()
        self.panel = newPanel

        // Slide in from the right edge while fading the SwiftUI content in.
        // We animate the NSPanel frame (AppKit) and the @Published opacity
        // (SwiftUI) in parallel — they have similar easing curves so the
        // motion reads as a single coordinated entrance.
        NSAnimationContext.runAnimationGroup({ context in
            context.duration = self.slideInDurationSeconds
            context.timingFunction = CAMediaTimingFunction(name: .easeOut)
            newPanel.animator().setFrame(finalFrame, display: true)
        }, completionHandler: nil)

        withAnimation(.easeOut(duration: fadeInDurationSeconds)) {
            hostState.currentPanelOpacity = 1.0
        }
    }

    private func ensurePanelIsAtFinalPosition(onScreen primaryScreen: NSScreen) {
        guard let panel else { return }
        let finalFrame = finalPanelFrame(onScreen: primaryScreen)
        if panel.frame != finalFrame {
            NSAnimationContext.runAnimationGroup({ context in
                context.duration = 0.25
                context.timingFunction = CAMediaTimingFunction(name: .easeOut)
                panel.animator().setFrame(finalFrame, display: true)
            }, completionHandler: nil)
        }
    }

    private func ensurePanelIsFullyOpaque() {
        if hostState.currentPanelOpacity < 1.0 {
            withAnimation(.easeOut(duration: fadeInDurationSeconds)) {
                hostState.currentPanelOpacity = 1.0
            }
        }
    }

    /// Top-right anchored panel frame in global AppKit coordinates.
    /// AppKit's y-axis is bottom-up so "top" means `visibleFrame.maxY`.
    private func finalPanelFrame(onScreen primaryScreen: NSScreen) -> NSRect {
        let visibleFrame = primaryScreen.visibleFrame
        let originX = visibleFrame.maxX - panelWidth - panelEdgeInset
        let originY = visibleFrame.maxY - panelHeight - panelEdgeInset
        return NSRect(x: originX, y: originY, width: panelWidth, height: panelHeight)
    }

    // MARK: - Hold + fade-out lifecycle

    /// Hold the panel on screen for `severity.totalOnScreenDurationSeconds`,
    /// then fade out and dispose of the panel. The task is cancelled (and
    /// replaced) if a new verdict arrives mid-display.
    private func scheduleHoldAndFadeOut(forSeverity severity: WarningGlyphSeverity) {
        let holdDurationSeconds = severity.totalOnScreenDurationSeconds
        let fadeDurationSeconds = self.fadeOutDurationSeconds

        displayLifecycleTask = Task { [weak self] in
            // Hold-on-screen window. Subtract the fade duration so the
            // overall presence (slide-in + hold + fade-out) lines up with
            // severity.totalOnScreenDurationSeconds.
            let nanosToHold = UInt64(max(0, holdDurationSeconds - fadeDurationSeconds) * 1_000_000_000)
            try? await Task.sleep(nanoseconds: nanosToHold)
            guard !Task.isCancelled else { return }

            await self?.fadeOutAndDisposeOfPanel(fadeDurationSeconds: fadeDurationSeconds)
        }
    }

    private func fadeOutAndDisposeOfPanel(fadeDurationSeconds: TimeInterval) async {
        guard panel != nil else { return }

        withAnimation(.easeIn(duration: fadeDurationSeconds)) {
            hostState.currentPanelOpacity = 0.0
        }

        // Wait for the SwiftUI fade to finish before we orderOut the panel,
        // otherwise the disappearance is instant on the trailing edge.
        let nanosToWaitForFade = UInt64(fadeDurationSeconds * 1_000_000_000)
        try? await Task.sleep(nanoseconds: nanosToWaitForFade)
        guard !Task.isCancelled else { return }

        if let panel = panel {
            panel.orderOut(nil)
            panel.contentView = nil
            self.panel = nil
        }
    }
}
