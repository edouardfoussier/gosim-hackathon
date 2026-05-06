//
//  WakeWordModelLoader.swift
//  leanring-buddy
//
//  Resolves on-disk locations for the three ONNX models that drive Xiexie's
//  always-on "Xiexie" wake-word detector. We bundle the two public openWakeWord
//  feature models (mel-spectrogram + Google speech-embedding) inside the app
//  bundle, but the custom classifier (`xiexie.onnx`) is large/private and
//  trained per-developer, so we look it up in a few candidate locations and
//  let the user drop it into Application Support without rebuilding.
//

import Foundation

enum WakeWordModelLoaderError: LocalizedError {
    case bundledModelMissing(filename: String)
    case classifierModelMissing(searchedPaths: [URL])

    var errorDescription: String? {
        switch self {
        case .bundledModelMissing(let filename):
            return "Wake-word: bundled model '\(filename)' is missing from the app bundle. Did the openWakeWord feature models get copied into the .app's Resources?"
        case .classifierModelMissing(let searchedPaths):
            let pathsList = searchedPaths.map { "  - \($0.path)" }.joined(separator: "\n")
            return """
            Wake-word: couldn't find xiexie.onnx in any of the expected locations.
            Drop the trained classifier into one of:
            \(pathsList)
            """
        }
    }
}

/// Resolves on-disk URLs for the three ONNX files that the wake-word pipeline
/// needs. The two openWakeWord feature models ship in the app bundle. The
/// trained Xiexie classifier (`xiexie.onnx`) can either ship inside the app
/// bundle or live in a writable Application Support directory so engineers can
/// drop in fresh classifiers without recompiling.
///
/// Static methods only — marked `nonisolated` so it can be called from any
/// context without dragging in the project-wide `MainActor` default isolation.
nonisolated enum WakeWordModelLoader {
    /// Filename of the openWakeWord mel-spectrogram model. Public, ~1.0 MB.
    /// Bundled with the app under `Resources/`.
    static let melSpectrogramFilename = "melspectrogram.onnx"

    /// Filename of the openWakeWord Google speech-embedding model. Public, ~1.3 MB.
    /// Bundled with the app under `Resources/`.
    static let embeddingFilename = "embedding_model.onnx"

    /// Filename of the trained Xiexie classifier (custom-trained).
    /// Searched in the app bundle and in `~/Library/Application Support/Xiexie/`.
    static let classifierFilename = "xiexie.onnx"

    /// Resolves the bundled mel-spectrogram model URL or throws if missing.
    static func resolveMelSpectrogramURL() throws -> URL {
        try resolveBundledModelURL(filename: Self.melSpectrogramFilename)
    }

    /// Resolves the bundled speech-embedding model URL or throws if missing.
    static func resolveEmbeddingModelURL() throws -> URL {
        try resolveBundledModelURL(filename: Self.embeddingFilename)
    }

    /// Resolves the trained Xiexie classifier URL by searching:
    ///   1. The app bundle (Resources)
    ///   2. `~/Library/Application Support/Xiexie/xiexie.onnx`
    ///   3. `~/Library/Application Support/ai.xiexie.app/xiexie.onnx`
    /// Returns nil if the classifier is not yet present so the rest of the app
    /// (ctrl+option fallback path) can keep working.
    static func locateClassifierModelURL() -> URL? {
        let bundleCandidate = Bundle.main.url(
            forResource: (Self.classifierFilename as NSString).deletingPathExtension,
            withExtension: (Self.classifierFilename as NSString).pathExtension
        )
        if let bundleCandidate, FileManager.default.fileExists(atPath: bundleCandidate.path) {
            return bundleCandidate
        }

        for candidateURL in classifierExternalSearchPaths() {
            if FileManager.default.fileExists(atPath: candidateURL.path) {
                return candidateURL
            }
        }

        return nil
    }

    /// Returns the writable disk locations the loader checks (in order) for
    /// the trained classifier. Used both for runtime lookup and for emitting
    /// helpful "drop the file here" error messages.
    static func classifierExternalSearchPaths() -> [URL] {
        guard let applicationSupportDirectoryURL = try? FileManager.default.url(
            for: .applicationSupportDirectory,
            in: .userDomainMask,
            appropriateFor: nil,
            create: false
        ) else {
            return []
        }

        return [
            applicationSupportDirectoryURL
                .appendingPathComponent("Xiexie", isDirectory: true)
                .appendingPathComponent(Self.classifierFilename),
            applicationSupportDirectoryURL
                .appendingPathComponent("ai.xiexie.app", isDirectory: true)
                .appendingPathComponent(Self.classifierFilename),
        ]
    }

    private static func resolveBundledModelURL(filename: String) throws -> URL {
        let baseName = (filename as NSString).deletingPathExtension
        let pathExtension = (filename as NSString).pathExtension

        if let bundledURL = Bundle.main.url(forResource: baseName, withExtension: pathExtension) {
            return bundledURL
        }

        // Try a `Resources/` subfolder explicitly, in case the bundle layout
        // ends up putting the .onnx files in a subdirectory.
        if let bundledURL = Bundle.main.url(
            forResource: baseName,
            withExtension: pathExtension,
            subdirectory: "Resources"
        ) {
            return bundledURL
        }

        throw WakeWordModelLoaderError.bundledModelMissing(filename: filename)
    }
}
