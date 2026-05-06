//
//  OpenWakeWordPipeline.swift
//  leanring-buddy
//
//  Streaming openWakeWord inference pipeline. Mirrors the Python streaming
//  reference in `openwakeword/utils.py::AudioFeatures` so the trained
//  classifier behaves identically on-device.
//
//  Audio flow (one direction, all on a serial worker queue):
//      raw 16 kHz PCM-16 frames
//          → mel-spectrogram model (every 80 ms / 1280 samples)
//          → Google speech-embedding model (one new 96-d vector per chunk)
//          → trained Xiexie classifier (16 most-recent embeddings → score)
//
//  The pipeline is **stateful**: it owns rolling buffers for raw audio,
//  mel frames, and speech embeddings. Each call to `processAudioSamples` may
//  produce zero, one, or several new classifier scores depending on how much
//  audio was buffered.
//
//  Important: `OpenWakeWordPipeline` does NOT perform any threading, lock, or
//  audio capture itself. It is a pure inference object meant to be driven by a
//  single worker queue. See `WakeWordDetector` for the concurrency wrapper.
//

import Foundation
import OnnxRuntimeBindings

enum OpenWakeWordPipelineError: LocalizedError {
    case missingClassifierModel
    case onnxRuntimeError(String)
    case unexpectedTensorShape(modelName: String, shape: [NSNumber])

    var errorDescription: String? {
        switch self {
        case .missingClassifierModel:
            return "Wake-word pipeline: the Xiexie classifier model is missing. Drop xiexie.onnx into Application Support/Xiexie/."
        case .onnxRuntimeError(let message):
            return "Wake-word pipeline: ONNX Runtime error — \(message)"
        case .unexpectedTensorShape(let modelName, let shape):
            return "Wake-word pipeline: unexpected output shape from \(modelName) — \(shape)"
        }
    }
}

/// Stateful streaming pipeline that turns raw 16 kHz PCM-16 audio into
/// "Xiexie" wake-word confidence scores.
///
/// Designed to mirror the `_streaming_features` + `predict` flow in
/// openWakeWord's Python implementation as exactly as is reasonable, so a
/// classifier trained against that runtime behaves the same when shipped here.
///
/// Marked `nonisolated` so the inference worker can drive it from a private
/// serial queue without the compiler inferring main-actor isolation from the
/// project-wide `SWIFT_DEFAULT_ACTOR_ISOLATION = MainActor` build setting.
/// All callers are responsible for serialising access (the worker uses one
/// dispatch queue).
nonisolated final class OpenWakeWordPipeline {
    /// 80 ms of 16 kHz audio = 1280 PCM-16 samples per processing chunk.
    /// openWakeWord is hard-coded to this granularity and we follow suit so
    /// the trained classifier sees the same temporal alignment.
    static let audioChunkSampleCount: Int = 1280

    /// 30 ms of audio (160 samples × 3 = 480 samples) of pre-padding context
    /// when computing the mel-spectrogram of the most recent 80 ms chunk.
    /// Matches `n_samples + 160*3` in the Python reference.
    static let melSpectrogramPaddingSampleCount: Int = 160 * 3

    /// Number of mel bins produced by `melspectrogram.onnx`. Hard-coded by
    /// the model architecture.
    static let melSpectrogramBinCount: Int = 32

    /// Number of mel frames required for one Google speech-embedding lookup.
    static let embeddingMelFrameWindowSize: Int = 76

    /// Output dimensionality of `embedding_model.onnx`.
    static let embeddingDimensionCount: Int = 96

    /// Number of recent embeddings the classifier consumes as one input row.
    /// 16 is the openWakeWord training default.
    static let classifierEmbeddingFrameCount: Int = 16

    /// Apply the same arbitrary scalar transform the Python reference applies
    /// to the mel-spectrogram before feeding it to the embedding model. This
    /// matches the comment in `openwakeword/utils.py::_get_melspectrogram`
    /// where it normalises the ONNX model's output to look more like the
    /// original Tensorflow speech-embedding inputs.
    private static let melSpectrogramScalarTransform: (Float) -> Float = { ($0 / 10.0) + 2.0 }

    /// Maximum number of mel frames retained in the rolling buffer. Mirrors
    /// the Python reference (`10 * 97`).
    private static let melSpectrogramBufferMaxFrameCount: Int = 10 * 97

    /// Maximum number of speech embeddings retained in the rolling buffer.
    /// Mirrors the Python reference (`feature_buffer_max_len = 120`).
    private static let embeddingFeatureBufferMaxFrameCount: Int = 120

    private let melSpectrogramSession: ORTSession
    private let melSpectrogramInputName: String
    private let melSpectrogramOutputName: String

    private let embeddingSession: ORTSession
    private let embeddingInputName: String
    private let embeddingOutputName: String

    private let classifierSession: ORTSession
    private let classifierInputName: String
    private let classifierOutputName: String
    private let classifierExpectedFeatureFrameCount: Int

    /// Raw PCM-16 audio samples received but not yet processed because we don't
    /// have a full 80 ms chunk yet.
    private var pendingRawSamples: [Int16] = []

    /// Rolling buffer of recent 16 kHz PCM-16 samples used to compute mel
    /// spectrograms with proper pre-padding context. Capped at 10 seconds.
    private var rawAudioBuffer: [Int16] = []

    /// Rolling 2-D buffer of mel frames: outer index = time, inner = mel bin.
    /// Pre-seeded with ones to match the Python reference startup state.
    private var melSpectrogramFrameBuffer: [[Float]]

    /// Rolling 2-D buffer of speech embeddings: outer index = time, inner = 96.
    /// Pre-seeded with zeros so the classifier always gets a full 16-frame
    /// input even when very little audio has been observed.
    private var embeddingFeatureBuffer: [[Float]]

    init(
        melSpectrogramModelURL: URL,
        embeddingModelURL: URL,
        classifierModelURL: URL,
        ortEnvironment: ORTEnv
    ) throws {
        let sessionOptions = try ORTSessionOptions()
        // Single-threaded inference is plenty for these tiny models — keeps
        // CPU usage predictable on the always-on path.
        try sessionOptions.setIntraOpNumThreads(1)

        do {
            self.melSpectrogramSession = try ORTSession(
                env: ortEnvironment,
                modelPath: melSpectrogramModelURL.path,
                sessionOptions: sessionOptions
            )
            self.melSpectrogramInputName = try Self.firstTensorName(of: self.melSpectrogramSession, isInput: true)
            self.melSpectrogramOutputName = try Self.firstTensorName(of: self.melSpectrogramSession, isInput: false)

            self.embeddingSession = try ORTSession(
                env: ortEnvironment,
                modelPath: embeddingModelURL.path,
                sessionOptions: sessionOptions
            )
            self.embeddingInputName = try Self.firstTensorName(of: self.embeddingSession, isInput: true)
            self.embeddingOutputName = try Self.firstTensorName(of: self.embeddingSession, isInput: false)

            self.classifierSession = try ORTSession(
                env: ortEnvironment,
                modelPath: classifierModelURL.path,
                sessionOptions: sessionOptions
            )
            self.classifierInputName = try Self.firstTensorName(of: self.classifierSession, isInput: true)
            self.classifierOutputName = try Self.firstTensorName(of: self.classifierSession, isInput: false)
        } catch {
            throw OpenWakeWordPipelineError.onnxRuntimeError(error.localizedDescription)
        }

        // Most openWakeWord classifiers are trained on 16-embedding context
        // windows. We default to 16; if a future trained model wants a
        // different context length, this constant becomes a model-side input.
        self.classifierExpectedFeatureFrameCount = Self.classifierEmbeddingFrameCount

        self.melSpectrogramFrameBuffer = Array(
            repeating: Array(repeating: 1.0, count: Self.melSpectrogramBinCount),
            count: Self.embeddingMelFrameWindowSize
        )
        self.embeddingFeatureBuffer = Array(
            repeating: Array(repeating: 0.0, count: Self.embeddingDimensionCount),
            count: Self.classifierEmbeddingFrameCount
        )
    }

    /// Resets all rolling buffers. Call when the listener is paused/resumed
    /// or after a wake-word fires so we don't immediately re-trigger on the
    /// audio that follows.
    func reset() {
        pendingRawSamples.removeAll(keepingCapacity: true)
        rawAudioBuffer.removeAll(keepingCapacity: true)
        melSpectrogramFrameBuffer = Array(
            repeating: Array(repeating: 1.0, count: Self.melSpectrogramBinCount),
            count: Self.embeddingMelFrameWindowSize
        )
        embeddingFeatureBuffer = Array(
            repeating: Array(repeating: 0.0, count: Self.embeddingDimensionCount),
            count: Self.classifierEmbeddingFrameCount
        )
    }

    /// Feeds raw PCM-16 samples (16 kHz mono) into the pipeline. Returns the
    /// classifier confidence scores for each new 80 ms chunk that finished
    /// processing during this call. Most calls return 0 or 1 score.
    @discardableResult
    func processAudioSamples(_ pcm16Samples: [Int16]) throws -> [Float] {
        guard !pcm16Samples.isEmpty else { return [] }

        pendingRawSamples.append(contentsOf: pcm16Samples)

        var newClassifierScores: [Float] = []

        while pendingRawSamples.count >= Self.audioChunkSampleCount {
            let chunkSamples = Array(pendingRawSamples.prefix(Self.audioChunkSampleCount))
            pendingRawSamples.removeFirst(Self.audioChunkSampleCount)

            try processSingleAudioChunk(chunkSamples: chunkSamples)

            let score = try runWakeWordClassifierOnLatestEmbeddings()
            newClassifierScores.append(score)
        }

        return newClassifierScores
    }

    // MARK: - Per-chunk pipeline

    private func processSingleAudioChunk(chunkSamples: [Int16]) throws {
        rawAudioBuffer.append(contentsOf: chunkSamples)
        let rollingRawBufferMaxSampleCount = 16_000 * 10
        if rawAudioBuffer.count > rollingRawBufferMaxSampleCount {
            rawAudioBuffer.removeFirst(rawAudioBuffer.count - rollingRawBufferMaxSampleCount)
        }

        let melSpectrogramInputSamples = sliceForMelSpectrogramInput()
        let newMelFrames = try runMelSpectrogramOnSamples(melSpectrogramInputSamples)

        for melFrame in newMelFrames {
            melSpectrogramFrameBuffer.append(melFrame)
        }
        if melSpectrogramFrameBuffer.count > Self.melSpectrogramBufferMaxFrameCount {
            melSpectrogramFrameBuffer.removeFirst(
                melSpectrogramFrameBuffer.count - Self.melSpectrogramBufferMaxFrameCount
            )
        }

        if melSpectrogramFrameBuffer.count >= Self.embeddingMelFrameWindowSize {
            let embeddingMelWindow = Array(
                melSpectrogramFrameBuffer.suffix(Self.embeddingMelFrameWindowSize)
            )
            let newEmbedding = try runSpeechEmbeddingOnMelWindow(embeddingMelWindow)
            embeddingFeatureBuffer.append(newEmbedding)
            if embeddingFeatureBuffer.count > Self.embeddingFeatureBufferMaxFrameCount {
                embeddingFeatureBuffer.removeFirst(
                    embeddingFeatureBuffer.count - Self.embeddingFeatureBufferMaxFrameCount
                )
            }
        }
    }

    private func sliceForMelSpectrogramInput() -> [Int16] {
        let desiredSampleCount = Self.audioChunkSampleCount + Self.melSpectrogramPaddingSampleCount
        if rawAudioBuffer.count <= desiredSampleCount {
            return rawAudioBuffer
        }
        return Array(rawAudioBuffer.suffix(desiredSampleCount))
    }

    // MARK: - ONNX model invocations

    private func runMelSpectrogramOnSamples(_ pcm16Samples: [Int16]) throws -> [[Float]] {
        let floatSamples = pcm16Samples.map { Float($0) }
        let inputShape: [NSNumber] = [1, NSNumber(value: floatSamples.count)]

        let inputData = NSMutableData(
            bytes: floatSamples,
            length: floatSamples.count * MemoryLayout<Float>.size
        )

        let inputTensor: ORTValue
        do {
            inputTensor = try ORTValue(
                tensorData: inputData,
                elementType: .float,
                shape: inputShape
            )
        } catch {
            throw OpenWakeWordPipelineError.onnxRuntimeError(
                "couldn't build mel-spectrogram input tensor: \(error.localizedDescription)"
            )
        }

        let outputs: [String: ORTValue]
        do {
            outputs = try melSpectrogramSession.run(
                withInputs: [melSpectrogramInputName: inputTensor],
                outputNames: Set([melSpectrogramOutputName]),
                runOptions: nil
            )
        } catch {
            throw OpenWakeWordPipelineError.onnxRuntimeError(
                "mel-spectrogram inference failed: \(error.localizedDescription)"
            )
        }

        guard let melTensor = outputs[melSpectrogramOutputName] else {
            throw OpenWakeWordPipelineError.onnxRuntimeError(
                "mel-spectrogram output tensor missing from ONNX output map"
            )
        }

        let outputTensorTypeAndShape = try melTensor.tensorTypeAndShapeInfo()
        let outputTensorShape = outputTensorTypeAndShape.shape

        let melFloatBytes = try melTensor.tensorData() as Data
        let melFloatValues = melFloatBytes.withUnsafeBytes { rawBufferPointer -> [Float] in
            let floatBuffer = rawBufferPointer.bindMemory(to: Float.self)
            return Array(floatBuffer)
        }

        // The mel-spectrogram model returns shape [time, 1, 1, 32] (with two
        // size-1 axes that the Python reference squeezes away). We treat any
        // axis equal to `melSpectrogramBinCount` as the bin axis, and assume
        // the remaining product over the other axes is the number of frames.
        let totalFloatCount = melFloatValues.count
        guard totalFloatCount > 0,
              totalFloatCount % Self.melSpectrogramBinCount == 0 else {
            throw OpenWakeWordPipelineError.unexpectedTensorShape(
                modelName: "melspectrogram.onnx",
                shape: outputTensorShape
            )
        }

        let frameCount = totalFloatCount / Self.melSpectrogramBinCount
        var melFrames: [[Float]] = []
        melFrames.reserveCapacity(frameCount)

        for frameIndex in 0..<frameCount {
            let frameStart = frameIndex * Self.melSpectrogramBinCount
            let frameEnd = frameStart + Self.melSpectrogramBinCount
            var frameValues = Array(melFloatValues[frameStart..<frameEnd])
            for binIndex in 0..<frameValues.count {
                frameValues[binIndex] = Self.melSpectrogramScalarTransform(frameValues[binIndex])
            }
            melFrames.append(frameValues)
        }

        return melFrames
    }

    private func runSpeechEmbeddingOnMelWindow(_ melFrameWindow: [[Float]]) throws -> [Float] {
        var flattenedMelValues: [Float] = []
        flattenedMelValues.reserveCapacity(
            Self.embeddingMelFrameWindowSize * Self.melSpectrogramBinCount
        )
        for frame in melFrameWindow {
            flattenedMelValues.append(contentsOf: frame)
        }

        let inputShape: [NSNumber] = [
            1,
            NSNumber(value: Self.embeddingMelFrameWindowSize),
            NSNumber(value: Self.melSpectrogramBinCount),
            1
        ]
        let inputData = NSMutableData(
            bytes: flattenedMelValues,
            length: flattenedMelValues.count * MemoryLayout<Float>.size
        )

        let inputTensor: ORTValue
        do {
            inputTensor = try ORTValue(
                tensorData: inputData,
                elementType: .float,
                shape: inputShape
            )
        } catch {
            throw OpenWakeWordPipelineError.onnxRuntimeError(
                "couldn't build embedding input tensor: \(error.localizedDescription)"
            )
        }

        let outputs: [String: ORTValue]
        do {
            outputs = try embeddingSession.run(
                withInputs: [embeddingInputName: inputTensor],
                outputNames: Set([embeddingOutputName]),
                runOptions: nil
            )
        } catch {
            throw OpenWakeWordPipelineError.onnxRuntimeError(
                "embedding inference failed: \(error.localizedDescription)"
            )
        }

        guard let embeddingTensor = outputs[embeddingOutputName] else {
            throw OpenWakeWordPipelineError.onnxRuntimeError(
                "embedding output tensor missing from ONNX output map"
            )
        }

        let embeddingFloatBytes = try embeddingTensor.tensorData() as Data
        let embeddingFloatValues = embeddingFloatBytes.withUnsafeBytes { rawBufferPointer -> [Float] in
            let floatBuffer = rawBufferPointer.bindMemory(to: Float.self)
            return Array(floatBuffer)
        }

        guard embeddingFloatValues.count >= Self.embeddingDimensionCount else {
            throw OpenWakeWordPipelineError.unexpectedTensorShape(
                modelName: "embedding_model.onnx",
                shape: try embeddingTensor.tensorTypeAndShapeInfo().shape
            )
        }

        return Array(embeddingFloatValues.suffix(Self.embeddingDimensionCount))
    }

    private func runWakeWordClassifierOnLatestEmbeddings() throws -> Float {
        let frameCount = classifierExpectedFeatureFrameCount
        let recentEmbeddings = Array(embeddingFeatureBuffer.suffix(frameCount))
        guard recentEmbeddings.count == frameCount else {
            // Not enough embeddings yet to form a full classifier window;
            // shouldn't happen because we pre-seed the buffer, but defend
            // against it returning a noisy score anyway.
            return 0.0
        }

        var flattenedEmbeddingValues: [Float] = []
        flattenedEmbeddingValues.reserveCapacity(frameCount * Self.embeddingDimensionCount)
        for embedding in recentEmbeddings {
            flattenedEmbeddingValues.append(contentsOf: embedding)
        }

        let inputShape: [NSNumber] = [
            1,
            NSNumber(value: frameCount),
            NSNumber(value: Self.embeddingDimensionCount)
        ]
        let inputData = NSMutableData(
            bytes: flattenedEmbeddingValues,
            length: flattenedEmbeddingValues.count * MemoryLayout<Float>.size
        )

        let inputTensor: ORTValue
        do {
            inputTensor = try ORTValue(
                tensorData: inputData,
                elementType: .float,
                shape: inputShape
            )
        } catch {
            throw OpenWakeWordPipelineError.onnxRuntimeError(
                "couldn't build classifier input tensor: \(error.localizedDescription)"
            )
        }

        let outputs: [String: ORTValue]
        do {
            outputs = try classifierSession.run(
                withInputs: [classifierInputName: inputTensor],
                outputNames: Set([classifierOutputName]),
                runOptions: nil
            )
        } catch {
            throw OpenWakeWordPipelineError.onnxRuntimeError(
                "classifier inference failed: \(error.localizedDescription)"
            )
        }

        guard let classifierTensor = outputs[classifierOutputName] else {
            throw OpenWakeWordPipelineError.onnxRuntimeError(
                "classifier output tensor missing from ONNX output map"
            )
        }

        let scoreFloatBytes = try classifierTensor.tensorData() as Data
        let scoreFloatValues = scoreFloatBytes.withUnsafeBytes { rawBufferPointer -> [Float] in
            let floatBuffer = rawBufferPointer.bindMemory(to: Float.self)
            return Array(floatBuffer)
        }

        // Most openWakeWord classifiers emit a single confidence score per
        // call. If the model emits more (e.g., multiple wake words at once)
        // we just return the maximum, which is the right reading for "did the
        // user say Xiexie?".
        return scoreFloatValues.max() ?? 0.0
    }

    // MARK: - ORT helpers

    private static func firstTensorName(of session: ORTSession, isInput: Bool) throws -> String {
        let names: [String]
        if isInput {
            names = try session.inputNames()
        } else {
            names = try session.outputNames()
        }
        guard let first = names.first else {
            throw OpenWakeWordPipelineError.onnxRuntimeError(
                "ONNX session reported no \(isInput ? "input" : "output") tensors"
            )
        }
        return first
    }
}
