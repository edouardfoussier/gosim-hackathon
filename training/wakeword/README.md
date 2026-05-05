# Xiexie wake-word — openWakeWord training pipeline

This folder produces `xiexie.onnx`, the custom wake-word model that lets the
backend listen for "Xiexie" with **no API key, no cloud, no commercial-approval
gate** (unlike Picovoice). The runtime stack is at
`backend/xiexie/voice/wake.py`; this folder is just the offline training rig.

> ~30 min of your time + ~3–5 h of unattended Colab T4 wall-clock = a working
> custom wake-word.

## Files

| Path                                | What it is |
|-------------------------------------|------------|
| `record_samples.py`                 | macOS CLI that records 30–50 of *your* voice saying "Xiexie". |
| `xiexie_wakeword_training.ipynb`    | Self-contained Colab notebook: synth + train + eval + export. |
| `positives/`                        | Where `record_samples.py` writes WAVs (gitignored audio). |
| `README.md`                         | This file. |

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
afplay positives/sample_0000.wav   # macOS built-in player
```

### Step 2 — Upload positives to Drive (1 min)

```bash
zip -r positives.zip positives
```

Drag `positives.zip` into **`MyDrive/xiexie/positives.zip`** in your browser.

(If you skip this step the notebook still trains a synthetic-only model, but
quality drops noticeably — the model never sees your actual voice/mic/room.)

### Step 3 — Open Colab and run all cells (3–5 h on T4)

1. Open <https://colab.research.google.com>, **File → Upload notebook →**
   `xiexie_wakeword_training.ipynb`.
2. **Runtime → Change runtime type → T4 GPU**. (CPU works too — just ~10 h
   instead of 3–5.)
3. Edit the `CONFIG` cell at the top if you want a quicker smoke run
   (`n_samples_train=500`, `steps=5000` finishes in ~30 min on T4 but the model
   will be visibly weaker — fine for debugging the pipeline).
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

## Activation fallback chain

The backend picks the best wake-word backend it can find at startup.
Whichever step you skip, the next one keeps the demo alive:

| Tier | Asset present                                | Backend       | Notes |
|----|------------------------------------------------|---------------|-------|
| 1  | `models/xiexie_mac.ppn` + `PICOVOICE_ACCESS_KEY` | Picovoice (custom)   | Best quality, gated by Picovoice approval. |
| 2  | `models/xiexie.onnx`                            | **openWakeWord**     | Apache-2.0, local-first, no key. *This is the one this folder produces.* |
| 3  | only `PICOVOICE_ACCESS_KEY`                     | Picovoice ("computer") | Built-in fallback keyword — works for demo prep. |
| 4  | nothing                                          | none — PTT only      | `ctrl+option` push-to-talk in `voice/ptt.py`. |

You can override the lookup paths via env vars (`XIEXIE_OWW_PATH`,
`XIEXIE_PPN_PATH`) — useful for AB-testing two trained models side by side.

## Pitfalls (read before training)

* **Colab session limits.** Free-tier sessions disconnect after ~12 h of
  uptime and ~90 min of inactivity. Keep the tab focused, or train in chunks
  — every step in the notebook skips work that's already on disk, so a kicked
  session can be resumed by re-running all cells.
* **CPU vs T4 timing.** The dominant cost is `--train_model` (~2–4 h on T4,
  ~6–8 h on CPU). Generation is ~10 min on either. Augmentation is ~30 min.
* **GPU not detected?** First cell prints
  `cuda: True, device: Tesla T4` if so. If it's `cuda: False`, you forgot to
  switch the runtime — change it and **Runtime → Run all** again.
* **Drive ran out of space?** The notebook downloads ~5 GB of background audio
  + ~3 GB of pre-computed features into `/content/`. If your Drive is also
  full, the export step (~5 MB) will fail at the end — clear some Drive space
  before the eval cell finishes.
* **Synthetic-only training (no `positives.zip`).** Works, but expect noticeably
  higher false-rejects in the demo room because the model never saw your mic,
  your room reverb, or your voice. Always record a few dozen positives if you
  can.
* **macOS-only training is *not* supported.** The official openWakeWord
  pipeline ([`automatic_model_training.ipynb`](https://github.com/dscripka/openWakeWord/blob/main/notebooks/automatic_model_training.ipynb))
  hard-requires Linux because of `piper-sample-generator`. That's why this is
  a Colab notebook — the local Mac just records positives.
* **Threshold tuning.** The runtime defaults to `oww_threshold=0.5`. If the
  model false-fires in the noisy demo room, bump it (in `wake.py`); if it
  misses you on stage, lower it. Tune *before* the demo, not during.

## What we did *not* build (and why)

* **Live recording UI in the notebook** — adds dependencies (`pyaudio`,
  `gradio`) for ~zero benefit; the Mac CLI is faster and gives better-quality
  recordings.
* **In-notebook fine-tuning of an existing ONNX** — overkill for two-day
  hackathon scope; we always retrain from scratch.
* **A Picovoice path inside this folder** — Picovoice has its own console
  workflow at <https://console.picovoice.ai>; this folder's whole reason for
  existing is the *non-Picovoice* path.
