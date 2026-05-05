# Xiexie backend

Python FastAPI backend for Xiexie. Owns the planner, skill registry, voice
loop, and Karpathy LLM-Wiki memory.

## Quick start

```bash
# Once
uv sync                                    # install deps
cp ../.env.example ../.env                 # add ZAI_API_KEY (or OPENAI_API_KEY)

# Each session
uv run uvicorn xiexie.main:app --reload --port 8787
```

## Test a skill in isolation

```bash
uv run python -m xiexie.skills.open_app --app "Google Chrome"
uv run python -m xiexie.skills.find_file --query "EDF"
uv run python -m xiexie.skills.set_reminder --when "tomorrow 9am" --what "call Lisa"
```

## Run the linter pass manually

```bash
uv run python -m xiexie.memory.linter
```

## Structure

```
xiexie/
├── main.py            # FastAPI app + WebSocket bridge to UI
├── config.py          # env vars + paths
├── llm/               # provider abstraction (Z.AI GLM-4.6 / OpenAI fallback)
├── voice/             # STT (faster-whisper) + TTS (Kokoro / system `say`)
├── skills/            # 7 named skills + registry
├── memory/            # Karpathy LLM-Wiki R/W + linter
└── planner/           # voice text → skill selection (GLM tool calling)
```

See `../CLAUDE.md` for the full dev harness.
See `../WIKI_SCHEMA.md` for the runtime memory schema.
