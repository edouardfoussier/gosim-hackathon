"use client";

/**
 * Browser-side voice I/O helpers for Xiexie.
 *
 * - `MicRecorder` wraps `getUserMedia` + `MediaRecorder` and exposes a 0..1
 *   `audioLevel()` derived from a Web Audio `AnalyserNode` so the UI can
 *   render a tiny equaliser while Margaret is speaking.
 * - `TtsPlayer` wraps the platform `SpeechSynthesis` API with a serial queue
 *   so overlapping `speak`/`confirm` events don't talk over each other.
 *
 * No external dependencies — Web Audio + Web Speech are both in the DOM lib.
 */

const PREFERRED_MIME_TYPES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/ogg;codecs=opus",
  "audio/mp4",
];

function pickMimeType(): string | undefined {
  if (typeof MediaRecorder === "undefined") return undefined;
  for (const mime of PREFERRED_MIME_TYPES) {
    if (MediaRecorder.isTypeSupported(mime)) return mime;
  }
  return undefined;
}

export class MicRecorder {
  private stream: MediaStream | null = null;
  private recorder: MediaRecorder | null = null;
  private chunks: Blob[] = [];
  private audioContext: AudioContext | null = null;
  private analyser: AnalyserNode | null = null;
  private analyserBuffer: Uint8Array | null = null;
  private mimeType: string | undefined;
  private recording = false;

  isRecording(): boolean {
    return this.recording;
  }

  /** Request mic permission and start capturing. */
  async start(): Promise<void> {
    if (this.recording) return;
    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      throw new Error("getUserMedia is not available in this browser");
    }

    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    this.stream = stream;
    this.chunks = [];
    this.mimeType = pickMimeType();

    const recorder = this.mimeType
      ? new MediaRecorder(stream, { mimeType: this.mimeType })
      : new MediaRecorder(stream);

    recorder.addEventListener("dataavailable", (event) => {
      if (event.data && event.data.size > 0) this.chunks.push(event.data);
    });
    this.recorder = recorder;

    // Web Audio analyser for the UI level meter — independent of MediaRecorder
    // so we keep visuals smooth even if the recorder buffers in chunks.
    const AudioContextCtor =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext?: typeof AudioContext })
        .webkitAudioContext;
    if (AudioContextCtor) {
      const ctx = new AudioContextCtor();
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      analyser.smoothingTimeConstant = 0.6;
      source.connect(analyser);
      this.audioContext = ctx;
      this.analyser = analyser;
      this.analyserBuffer = new Uint8Array(analyser.frequencyBinCount);
    }

    recorder.start();
    this.recording = true;
  }

  /** Stop capture and return the recorded audio blob. */
  async stop(): Promise<Blob> {
    const recorder = this.recorder;
    if (!recorder || !this.recording) {
      return new Blob([], { type: this.mimeType ?? "audio/webm" });
    }

    const blob = await new Promise<Blob>((resolve) => {
      recorder.addEventListener(
        "stop",
        () => {
          const type = this.mimeType ?? recorder.mimeType ?? "audio/webm";
          resolve(new Blob(this.chunks, { type }));
        },
        { once: true }
      );
      recorder.stop();
    });

    this.recording = false;
    this.releaseStream();
    return blob;
  }

  /** Current input level in 0..1, derived from the time-domain RMS. */
  audioLevel(): number {
    if (!this.analyser || !this.analyserBuffer) return 0;
    // Buffer is ArrayBuffer-backed Uint8Array; cast for getByteTimeDomainData.
    this.analyser.getByteTimeDomainData(
      this.analyserBuffer as unknown as Uint8Array<ArrayBuffer>
    );
    let sumSquares = 0;
    for (let i = 0; i < this.analyserBuffer.length; i++) {
      const centered = (this.analyserBuffer[i] - 128) / 128;
      sumSquares += centered * centered;
    }
    const rms = Math.sqrt(sumSquares / this.analyserBuffer.length);
    return Math.min(1, rms * 2.2);
  }

  /** Release mic + audio context. Safe to call multiple times. */
  cleanup(): void {
    if (this.recorder && this.recording) {
      try {
        this.recorder.stop();
      } catch {
        /* ignore double-stop */
      }
    }
    this.recording = false;
    this.releaseStream();
  }

  private releaseStream(): void {
    if (this.stream) {
      for (const track of this.stream.getTracks()) track.stop();
      this.stream = null;
    }
    if (this.audioContext && this.audioContext.state !== "closed") {
      this.audioContext.close().catch(() => {
        /* ignore */
      });
    }
    this.audioContext = null;
    this.analyser = null;
    this.analyserBuffer = null;
    this.recorder = null;
  }
}

export interface TtsSpeakOptions {
  voice?: string;
  rate?: number;
  volume?: number;
}

interface QueueItem {
  text: string;
  opts: TtsSpeakOptions;
  resolve: () => void;
  reject: (err: unknown) => void;
}

/**
 * Senior-friendly defaults — slightly slower than browser default and full
 * volume. Voice selection prefers warm offline voices and respects the
 * `NEXT_PUBLIC_TTS_VOICE` env override.
 */
export class TtsPlayer {
  private queue: QueueItem[] = [];
  private cachedVoices: SpeechSynthesisVoice[] = [];
  private speaking = false;
  private envVoice: string | undefined;

  constructor(envVoice?: string) {
    this.envVoice = envVoice?.trim() || undefined;
    if (this.available()) {
      this.cachedVoices = window.speechSynthesis.getVoices();
      window.speechSynthesis.addEventListener("voiceschanged", () => {
        this.cachedVoices = window.speechSynthesis.getVoices();
      });
    }
  }

  isSpeaking(): boolean {
    return this.speaking;
  }

  available(): boolean {
    return typeof window !== "undefined" && "speechSynthesis" in window;
  }

  speak(text: string, opts: TtsSpeakOptions = {}): Promise<void> {
    if (!this.available()) return Promise.resolve();
    const trimmed = text.trim();
    if (!trimmed) return Promise.resolve();
    return new Promise<void>((resolve, reject) => {
      this.queue.push({ text: trimmed, opts, resolve, reject });
      this.drain();
    });
  }

  cancel(): void {
    if (!this.available()) return;
    const pending = this.queue.splice(0);
    window.speechSynthesis.cancel();
    this.speaking = false;
    for (const item of pending) item.resolve();
  }

  private drain(): void {
    if (this.speaking || this.queue.length === 0) return;
    const item = this.queue.shift()!;
    const utter = new SpeechSynthesisUtterance(item.text);
    const voice = this.pickVoice(item.opts.voice);
    if (voice) {
      utter.voice = voice;
      utter.lang = voice.lang;
    } else {
      utter.lang = "en-US";
    }
    utter.rate = item.opts.rate ?? 0.95;
    utter.volume = item.opts.volume ?? 1.0;
    utter.pitch = 1.0;

    this.speaking = true;
    utter.onend = () => {
      this.speaking = false;
      item.resolve();
      this.drain();
    };
    utter.onerror = (event) => {
      this.speaking = false;
      // `interrupted`/`canceled` happen during normal `cancel()` flows; treat
      // as a soft success so the caller's promise still resolves cleanly.
      if (event.error === "interrupted" || event.error === "canceled") {
        item.resolve();
      } else {
        item.reject(new Error(`tts error: ${event.error}`));
      }
      this.drain();
    };

    try {
      window.speechSynthesis.speak(utter);
    } catch (err) {
      this.speaking = false;
      item.reject(err);
      this.drain();
    }
  }

  private pickVoice(explicit?: string): SpeechSynthesisVoice | undefined {
    if (!this.cachedVoices.length && this.available()) {
      this.cachedVoices = window.speechSynthesis.getVoices();
    }
    const voices = this.cachedVoices;
    if (!voices.length) return undefined;

    const byName = (name: string) =>
      voices.find((v) => v.name.toLowerCase() === name.toLowerCase());

    if (explicit) {
      const hit = byName(explicit);
      if (hit) return hit;
    }
    if (this.envVoice) {
      const hit = byName(this.envVoice);
      if (hit) return hit;
    }

    const samantha = byName("Samantha");
    if (samantha) return samantha;
    const karen = byName("Karen");
    if (karen) return karen;

    const localUS = voices.find(
      (v) => v.lang === "en-US" && v.localService === true
    );
    if (localUS) return localUS;

    return voices[0];
  }
}
