# openWakeWord patches for Colab Python 3.12

The Colab default runtime moved to **Python 3.12** in August 2025. The original
training pipeline (`automatic_model_training.ipynb`) hard-pins three packages
that no longer have py3.12 wheels:

| Package | Where | Why dropped |
|---|---|---|
| `speexdsp-ns>=0.1.2,<1` | `setup.py` (Linux only `install_requires`) | C extension; only one cp310 wheel ever published (2023). On py3.12 pip falls back to a from-source build that needs `libspeexdsp-dev` apt headers. We only use **noise suppression at training time via `audiomentations`**, never `speexdsp-ns` — safe to drop. |
| `tensorflow-cpu==2.8.1` | training extras | TF 2.8 is cp310-only. Used **only** by `--convert_to_tflite` (opt-in), which we do not call: the runtime in `backend/xiexie/voice/wake.py` consumes ONNX, not TFLite. |
| `tensorflow_probability==0.16.0` + `onnx_tf==1.10.0` | training extras | Same — only used by `--convert_to_tflite`. |
| `piper-phonemize` | top-level pip | No py3.12 wheel, no maintained build. The new **`piper-sample-generator>=3.2.0`** (PyPI, March 2026) bundles `piper-tts==1.4.x` which embeds espeak-ng directly, so this dep disappears entirely. |

## Files in this folder

* **`setup.patch`** — single-line removal of `speexdsp-ns` from
  `setup.py`'s `install_requires`. Apply with `git apply` against a fresh
  clone of `https://github.com/dscripka/openWakeWord` at HEAD (commit
  `368c037` or later, which already moved tflite conversion behind the
  `--convert_to_tflite` flag and dropped the `tflite-runtime` install).

The notebook cell **§ 1c** applies this patch automatically; you should not
need to run anything from this folder by hand.

## Why we do not also patch `train.py`

The notebook plants a small **shim file** at `/content/generate_samples.py`
that re-exports the modern `piper_sample_generator.generate_samples` with
the right `model=` argument injected. Since the openWakeWord trainer does
`sys.path.insert(0, config["piper_sample_generator_path"]); from
generate_samples import generate_samples`, this shim is picked up
transparently — no source-level patch to `train.py` required.

## Recreating the patch

If openWakeWord HEAD ever rebases past commit `368c037`, regenerate with:

```bash
cd /tmp && rm -rf openWakeWord
git clone https://github.com/dscripka/openWakeWord
cd openWakeWord
# edit setup.py to drop the speexdsp-ns line
git diff setup.py > path/to/training/wakeword/openwakeword_patches/setup.patch
```
