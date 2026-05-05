# Xiexie wake-word — openWakeWord training pipeline

> **Last verified working on Colab H100, Python 3.12.13 — May 5 2026.**
> Estimated wall-clock: **~75 min** (H100). Output: **`xiexie.onnx` ≈ 1.3 MB.**
> T4 also works (~3–5× longer). CPU also works (~6 h, painful — avoid).

This folder produces `xiexie.onnx`, the custom wake-word model that lets the
backend listen for "Xiexie" with **no API key, no cloud, no commercial-approval
gate** (unlike Picovoice). The runtime stack is at
`backend/xiexie/voice/wake.py`; this folder is just the offline training rig.

## What changed in this revision (May 2026)

The previous notebook broke on modern Colab (Python 3.12) for three reasons:

1. `pip install piper-phonemize` — only ever shipped cp310 wheels.
2. `pip install tensorflow-cpu==2.8.1` — cp310-only.
3. The `onnx_tf == 1.10.0` + `tensorflow_probability == 0.16.0` cascade —
   only needed for the opt-in TFLite export, which we never call.

**Fix**: pivot to the modern PyPI **`piper-sample-generator>=3.2.0`**
(March 2026), which bundles `piper-tts==1.4.x` with **espeak-ng embedded
in the wheel** — no separate `piper-phonemize` install. We also drop the
TensorFlow-cpu / `onnx_tf` / `tensorflow_probability` triplet entirely
because the runtime in `backend/xiexie/voice/wake.py` consumes ONNX
directly (the runtime tier chain is unchanged: custom `.ppn` → custom
`.onnx` → built-in Porcupine "computer" → PTT).

A one-line `setup.py` patch (drop `speexdsp-ns`, no py3.12 wheel) is the
only source change to upstream openWakeWord. See
[`openwakeword_patches/`](openwakeword_patches/) for the diff.

## Files

| Path | What it is |
|---|---|
| `record_samples.py` | macOS CLI that records 30–50 of *your* voice saying "Xiexie". |
| `xiexie_wakeword_training.ipynb` | Self-contained Colab notebook: synth + train + eval + export. |
| `openwakeword_patches/setup.patch` | One-line removal of `speexdsp-ns` from upstream's `install_requires`. |
| `openwakeword_patches/README.md` | Why each upstream pin had to go. |
| `positives/` | Where `record_samples.py` writes WAVs (gitignored audio). |
| `positives.zip` | Bundled positives for upload to Drive (gitignored audio). |
| `README.md` | This file. |

## Recipe

### Step 1 — Record local positives (4 min)

Done once on Edouard's Mac:

```bash
cd training/wakeword
uv run --project ../../backend python -m record_samples --count 40
```

You'll hear a beep, say "Xiexie", brief silence, beep, say "Xiexie", … 40 times.
Vary tone/speed/emphasis; keep the room quiet. WAVs land in `positives/` at
16 kHz mono int16.

Spot-check the audio:

```bash
afplay positives/sample_0000.wav
```

### Step 2 — Upload positives to Drive (1 min)

```bash
zip -r positives.zip positives
```

Drag `positives.zip` into **`MyDrive/xiexie/positives.zip`** in your browser.

(If you skip this step the notebook still trains a synthetic-only model, but
quality drops noticeably — the model never sees your actual voice/mic/room.)

### Step 3 — Open Colab and run all cells (~75 min on H100)

1. Open <https://colab.research.google.com>, **File → Upload notebook →**
   `xiexie_wakeword_training.ipynb`.
2. **Runtime → Change runtime type → H100 GPU, High-RAM ON, Python 3
   (3.12 default).** T4 also works (just slower).
3. Edit the `CONFIG` cell at the top if you want a quicker smoke run
   (`n_samples_train=500`, `steps=5000` finishes in ~25 min on H100 but
   the model will be visibly weaker — fine for debugging the pipeline).
4. **Runtime → Run all**.
5. The notebook will prompt once for Drive auth. Click through.
6. Walk away. Come back when the eval cell has printed recall + false-trigger.

The final cell drops `xiexie.onnx` into `MyDrive/xiexie/xiexie.onnx` along with
the YAML config and an `eval_summary.json` so future-you knows what produced
this model.

### Step 4 — Download the model into the repo (30 s)

```bash
# from the repo root
mkdir -p models
# Drag MyDrive/xiexie/xiexie.onnx → models/xiexie.onnx in Finder, OR:
# (with Drive Desktop installed) cp ~/.../Drive/xiexie/xiexie.onnx models/
```

### Step 5 — Restart the backend

```bash
cd backend
uv run uvicorn xiexie.main:app --reload
```

You should see:

```
[wake] xiexie.onnx loaded (openwakeword) — listening (frame=1280 @ 16000 Hz, threshold=0.50)
```

Say "Xiexie" near the mic. The activation callback fires and the rest of the
voice loop takes over. Done.

## Pipeline summary

```
piper-sample-generator (PyPI v3.2.x)
            │  uses piper-tts==1.4.x with espeak-ng baked in
            ▼
  /content/generate_samples.py     ◀── shim file written by notebook § 1c;
            │                          re-exports the modern function with
            │                          model=en_US-libritts_r-medium.pt injected
            ▼
  openwakeword/openwakeword/train.py --generate_clips
            │  (synth N "Xiexie" + N adversarial negatives)
            ▼
  + 8× user_recordings/sample_*.wav (oversampled into positive_train/)
            │
            ▼
  --augment_clips      RIRs (MIT) + noise (AudioSet shard, FMA)
            │          → openWakeWord features (.npy memmap)
            ▼
  --train_model        small DNN over Google speech-embedding features;
            │          early-stops on validation accuracy/recall/FP-per-hour
            ▼
  my_custom_model/xiexie/xiexie.onnx     (≈ 1.3 MB)
            │
            ▼
  → /content/drive/MyDrive/xiexie/xiexie.onnx
  → backend/xiexie/voice/wake.py loads at startup
```

## Activation fallback chain

The backend picks the best wake-word backend it can find at startup.
Whichever step you skip, the next one keeps the demo alive:

| Tier | Asset present | Backend | Notes |
|------|---------------|---------|-------|
| 1 | `models/xiexie_mac.ppn` + `PICOVOICE_ACCESS_KEY` | Picovoice (custom) | Best quality, gated by Picovoice approval. |
| 2 | `models/xiexie.onnx` | **openWakeWord** | Apache-2.0, local-first, no key. *This is the one this folder produces.* |
| 3 | only `PICOVOICE_ACCESS_KEY` | Picovoice ("computer") | Built-in fallback keyword — works for demo prep. |
| 4 | nothing | none — PTT only | `ctrl+option` push-to-talk in `voice/ptt.py`. |

You can override the lookup paths via env vars (`XIEXIE_OWW_PATH`,
`XIEXIE_PPN_PATH`) — useful for AB-testing two trained models side by side.

## Pitfalls (read before training)

* **Colab session limits.** Pro/Pro+ H100 sessions are good for ~24 h
  uptime. Free-tier T4 disconnects after ~12 h of uptime and ~90 min of
  inactivity — keep the tab focused, or train in chunks. Every step in the
  notebook **skips work that's already on disk**, so a kicked session can
  be resumed by re-running all cells.
* **GPU not detected?** § 1b prints
  `cuda: True, device: NVIDIA H100 80GB HBM3` (or `Tesla T4`) if so. If
  it's `cuda: False`, you forgot to switch the runtime — change it and
  **Runtime → Run all** again.
* **Drive ran out of space?** The notebook downloads ~5 GB of background
  audio + ~3 GB of pre-computed features into `/content/`. Drive only
  needs ~5 MB for the export step — but if your Drive is full the final
  copy will fail. Clear some Drive space before the eval cell finishes.
* **Synthetic-only training (no `positives.zip`).** Works, but expect
  noticeably higher false-rejects in the demo room because the model
  never saw your mic, your room reverb, or your voice. Always record a
  few dozen positives if you can.
* **macOS-only training is *not* supported.** The official openWakeWord
  pipeline ([`automatic_model_training.ipynb`](https://github.com/dscripka/openWakeWord/blob/main/notebooks/automatic_model_training.ipynb))
  hard-requires Linux because of `piper-tts` espeak-ng linkage. That's
  why this is a Colab notebook — the local Mac just records positives.
* **Threshold tuning.** The runtime defaults to `oww_threshold=0.5`. If
  the model false-fires in the noisy demo room, bump it (in `wake.py`);
  if it misses you on stage, lower it. Tune *before* the demo, not during.
* **`tts_batch_size`.** Default `64` fits comfortably on H100 80 GB. On
  T4 16 GB drop to `32`. The modern piper-sample-generator does not
  auto-reduce on OOM — it just crashes — so pre-tune in the `CONFIG`
  cell.

## What we did *not* build (and why)

* **Live recording UI in the notebook** — adds dependencies (`pyaudio`,
  `gradio`) for ~zero benefit; the Mac CLI is faster and gives
  better-quality recordings.
* **In-notebook fine-tuning of an existing ONNX** — overkill for two-day
  hackathon scope; we always retrain from scratch.
* **A Picovoice path inside this folder** — Picovoice has its own console
  workflow at <https://console.picovoice.ai>; this folder's whole reason
  for existing is the *non-Picovoice* path.
* **TFLite export.** The runtime uses `onnxruntime`, not LiteRT; the
  TFLite path is what dragged `tensorflow-cpu==2.8.1` into the picture
  in the first place. It remains available upstream behind
  `--convert_to_tflite` if a future use-case calls for it.
