//
//  WakeWordDetector.swift
//  leanring-buddy
//
//  Always-on background mic listener that watches for the "Xiexie" wake-word.
//  Audio capture happens on a dedicated AVAudioEngine instance; ONNX inference
//  happens on a private serial queue inside `WakeWordInferenceWorker`, never
//  on the main thread or the mic-tap thread.
//
//  Flow:
//      mic tap (audio thread) → PCM-16 16 kHz mono
//        → inferenceWorker.enqueueAudioSamples(...)  (serial worker queue)
//          → OpenWakeWordPipeline.processAudioSamples
//          → confidence score
//        → if score ≥ threshold: hop back to @MainActor → wakeWordDidFire
//
//  Privacy hard rule: ALL inference happens locally on-device. The raw mic
//  bytes are never sent anywhere — they stay inside this object and the
//  on-device ONNX runtime. Network calls only happen AFTER the wake-word
//  fires and the existing push-to-talk dictation flow takes over.
//

import AVFoundation
import Combine
import Foundation
import OnnxRuntimeBindings

/// Non-actor inference worker. Owns the ONNX pipeline + a private serial
/// dispatch queue. All `enqueue` / fire callbacks are thread-safe.
///
/// Marked `nonisolated` so it doesn't inherit the project's default
/// `SWIFT_DEFAULT_ACTOR_ISOLATION = MainActor` setting. All access is
/// serialised by the internal `inferenceQueue`.
nonisolated final class WakeWordInferenceWorker: @unchecked Sendable {
    /// Confidence threshold (0..1) above which we consider the wake-word
    /// detected. Matches the threshold used in the training notebook.
    static let wakeWordConfidenceThreshold: Float = 0.5

    /// Cooldown between two consecutive wake-word fires, to avoid double
    /// triggers when the user says "Xiexie, Xiexie..." or when the classifier
    /// score briefly stays above threshold across several chunks.
    static let postFireCooldownSeconds: TimeInterval = 1.5

    /// Called on the inference queue every time the classifier produces a new
    /// confidence score (~once per 80 ms while audio is flowing). Subscribers
    /// should hop to whichever queue they need.
    var onConfidenceScoreUpdate: ((Float) -> Void)?

    /// Called on the inference queue when a wake-word fires. Subscribers
    /// should hop to the main thread to drive the conversation flow.
    var onWakeWordFired: (() -> Void)?

    private let inferenceQueue = DispatchQueue(
        label: "ai.xiexie.wakeword.inference",
        qos: .userInitiated
    )

    private let openWakeWordPipeline: OpenWakeWordPipeline
    private var earliestNextFireWallClockDate: Date = .distantPast

    init(openWakeWordPipeline: OpenWakeWordPipeline) {
        self.openWakeWordPipeline = openWakeWordPipeline
    }

    /// Thread-safe entry point for new audio samples coming off the mic tap.
    /// Returns immediately; the heavy ONNX inference happens asynchronously
    /// on the inference queue.
    func enqueueAudioSamples(_ pcm16Samples: [Int16]) {
        let pipeline = openWakeWordPipeline
        inferenceQueue.async { [weak self] in
            guard let self else { return }
            do {
                let scores = try pipeline.processAudioSamples(pcm16Samples)
                for confidenceScore in scores {
                    self.onConfidenceScoreUpdate?(confidenceScore)
                    self.maybeFireWakeWordForScore(confidenceScore)
                }
            } catch {
                // Don't kill the listener for one bad chunk — log and keep going.
                print("⚠️ WakeWordInferenceWorker: inference error — \(error.localizedDescription)")
            }
        }
    }

    /// Resets all rolling buffers inside the pipeline. Call after a wake-word
    /// fires so the audio captured during the response doesn't immediately
    /// trigger another fire.
    func resetPipelineBuffers() {
        let pipeline = openWakeWordPipeline
        inferenceQueue.async {
            pipeline.reset()
        }
    }

    private func maybeFireWakeWordForScore(_ confidenceScore: Float) {
        guard confidenceScore >= Self.wakeWordConfidenceThreshold else { return }

        let now = Date()
        guard now >= earliestNextFireWallClockDate else { return }

        earliestNextFireWallClockDate = now.addingTimeInterval(Self.postFireCooldownSeconds)
        print("🔥 WakeWordInferenceWorker: fired — score = \(confidenceScore)")
        onWakeWordFired?()
    }
}

@MainActor
final class WakeWordDetector: ObservableObject {
    /// Emitted on @MainActor when the detector decides "Xiexie" was just
    /// spoken. Subscribers wire this to the same code path that ctrl+option
    /// press fires (CompanionManager.handleShortcutTransition(.pressed)).
    let wakeWordDidFire = PassthroughSubject<Void, Never>()

    /// Mostly-debug flag: was the detector successfully started? If false,
    /// the ctrl+option fallback path is the only way to invoke Xiexie.
    @Published private(set) var isListening: Bool = false

    /// Latest classifier confidence score we observed. Useful for UI debug
    /// indicators ("am I being heard?").
    @Published private(set) var latestConfidenceScore: Float = 0

    /// User-facing description of why the detector couldn't start, if anything
    /// went wrong during `start()`. Used by the panel UI for diagnostics.
    @Published private(set) var startupFailureReason: String?

    private let audioEngine = AVAudioEngine()
    private var audioFormatConverter: AVAudioConverter?
    private var inferenceWorker: WakeWordInferenceWorker?
    private var wakeWordOrtEnvironment: ORTEnv?

    deinit {
        audioEngine.stop()
        audioEngine.inputNode.removeTap(onBus: 0)
    }

    /// Starts the always-on listener. Safe to call repeatedly — does nothing
    /// if the listener is already running.
    func start() {
        guard !isListening else { return }

        startupFailureReason = nil

        do {
            try setupInferenceWorkerIfNeeded()
        } catch {
            print("⚠️ WakeWordDetector: failed to load ONNX pipeline — \(error.localizedDescription)")
            startupFailureReason = error.localizedDescription
            return
        }

        do {
            try installMicTapAndStartEngine()
        } catch {
            print("⚠️ WakeWordDetector: couldn't start audio engine — \(error.localizedDescription)")
            startupFailureReason = "couldn't start mic capture: \(error.localizedDescription)"
            return
        }

        isListening = true
        print("🎯 WakeWordDetector: listening for 'Xiexie' (threshold = \(WakeWordInferenceWorker.wakeWordConfidenceThreshold))")
    }

    /// Stops the listener and tears down the mic tap. The ONNX models stay
    /// loaded so a subsequent `start()` is fast.
    func stop() {
        guard isListening else { return }

        audioEngine.stop()
        audioEngine.inputNode.removeTap(onBus: 0)
        isListening = false
        latestConfidenceScore = 0
        print("🎯 WakeWordDetector: stopped listening")
    }

    /// Explicitly clears the rolling audio buffers inside the pipeline, e.g.
    /// after the wake-word fires and we don't want stale audio echoing into
    /// the next detection window.
    func resetPipelineBuffers() {
        inferenceWorker?.resetPipelineBuffers()
    }

    // MARK: - Setup

    private func setupInferenceWorkerIfNeeded() throws {
        guard inferenceWorker == nil else { return }

        let melSpectrogramURL = try WakeWordModelLoader.resolveMelSpectrogramURL()
        let embeddingURL = try WakeWordModelLoader.resolveEmbeddingModelURL()

        guard let classifierURL = WakeWordModelLoader.locateClassifierModelURL() else {
            let searchedExternalPaths = WakeWordModelLoader.classifierExternalSearchPaths()
            throw WakeWordModelLoaderError.classifierModelMissing(searchedPaths: searchedExternalPaths)
        }

        let ortEnvironment = try ORTEnv(loggingLevel: .warning)
        self.wakeWordOrtEnvironment = ortEnvironment

        let pipeline = try OpenWakeWordPipeline(
            melSpectrogramModelURL: melSpectrogramURL,
            embeddingModelURL: embeddingURL,
            classifierModelURL: classifierURL,
            ortEnvironment: ortEnvironment
        )

        let worker = WakeWordInferenceWorker(openWakeWordPipeline: pipeline)
        worker.onConfidenceScoreUpdate = { [weak self] confidenceScore in
            Task { @MainActor [weak self] in
                self?.latestConfidenceScore = confidenceScore
            }
        }
        worker.onWakeWordFired = { [weak self] in
            Task { @MainActor [weak self] in
                self?.wakeWordDidFire.send(())
            }
        }
        self.inferenceWorker = worker
    }

    private func installMicTapAndStartEngine() throws {
        let inputNode = audioEngine.inputNode
        let inputFormat = inputNode.outputFormat(forBus: 0)

        let targetSampleRate: Double = 16_000
        guard let targetFormat = AVAudioFormat(
            commonFormat: .pcmFormatInt16,
            sampleRate: targetSampleRate,
            channels: 1,
            interleaved: true
        ) else {
            throw NSError(
                domain: "ai.xiexie.wakeword",
                code: -1,
                userInfo: [NSLocalizedDescriptionKey: "couldn't build target PCM-16 format"]
            )
        }

        if inputFormat.sampleRate != targetSampleRate
            || inputFormat.channelCount != 1
            || inputFormat.commonFormat != .pcmFormatInt16 {
            self.audioFormatConverter = AVAudioConverter(from: inputFormat, to: targetFormat)
        } else {
            self.audioFormatConverter = nil
        }

        // 80 ms (1280 samples @ 16 kHz) is openWakeWord's natural granularity,
        // but we don't have to match that on the mic side. Larger buffers
        // reduce CPU load. We let AVAudioEngine pick a comfortable buffer
        // size and re-chunk inside the pipeline.
        let micTapBufferFrameCount: AVAudioFrameCount = 4096
        let formatConverterForTap = self.audioFormatConverter
        let inferenceWorkerForTap = self.inferenceWorker

        inputNode.removeTap(onBus: 0)
        inputNode.installTap(
            onBus: 0,
            bufferSize: micTapBufferFrameCount,
            format: inputFormat
        ) { capturedBuffer, _ in
            // Re-sample and convert to PCM-16 mono on the audio thread, then
            // ship just the small Int16 array off to the inference queue. We
            // never block the mic tap on ONNX inference.
            guard let pcm16Samples = Self.convertBufferToPCM16Mono16kHz(
                capturedBuffer,
                converter: formatConverterForTap,
                targetFormat: targetFormat
            ), !pcm16Samples.isEmpty else {
                return
            }

            inferenceWorkerForTap?.enqueueAudioSamples(pcm16Samples)
        }

        audioEngine.prepare()
        try audioEngine.start()
    }

    // MARK: - Audio format conversion

    /// Converts an AVAudioPCMBuffer of arbitrary input format into a flat
    /// `[Int16]` array of PCM-16 mono samples at 16 kHz, suitable for direct
    /// feeding into openWakeWord's mel-spectrogram model.
    private nonisolated static func convertBufferToPCM16Mono16kHz(
        _ inputBuffer: AVAudioPCMBuffer,
        converter: AVAudioConverter?,
        targetFormat: AVAudioFormat
    ) -> [Int16]? {
        if let converter {
            // Output capacity: at most 1× the original frame count when
            // upsampling, less when downsampling. We size for 2× safety so
            // converter.convert never trips on a too-small buffer.
            let outputCapacity = AVAudioFrameCount(
                Double(inputBuffer.frameLength) * 2.0 + 16
            )

            guard let outputBuffer = AVAudioPCMBuffer(
                pcmFormat: targetFormat,
                frameCapacity: outputCapacity
            ) else {
                return nil
            }

            var hasProvidedInput = false
            let inputProvider: AVAudioConverterInputBlock = { _, outStatus in
                if hasProvidedInput {
                    outStatus.pointee = .noDataNow
                    return nil
                }
                hasProvidedInput = true
                outStatus.pointee = .haveData
                return inputBuffer
            }

            var conversionError: NSError?
            let conversionStatus = converter.convert(
                to: outputBuffer,
                error: &conversionError,
                withInputFrom: inputProvider
            )

            if conversionStatus == .error {
                print("⚠️ WakeWordDetector: format conversion error — \(conversionError?.localizedDescription ?? "unknown")")
                return nil
            }

            return Self.flattenPCM16Buffer(outputBuffer)
        }

        return Self.flattenPCM16Buffer(inputBuffer)
    }

    private nonisolated static func flattenPCM16Buffer(_ buffer: AVAudioPCMBuffer) -> [Int16]? {
        guard let int16ChannelData = buffer.int16ChannelData else { return nil }
        let frameCount = Int(buffer.frameLength)
        guard frameCount > 0 else { return [] }

        let firstChannelPointer = int16ChannelData[0]
        var samples = [Int16](repeating: 0, count: frameCount)
        for sampleIndex in 0..<frameCount {
            samples[sampleIndex] = firstChannelPointer[sampleIndex]
        }
        return samples
    }
}
