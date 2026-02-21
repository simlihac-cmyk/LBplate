# Kkomantle Whitelist

`kkomantle_whitelist.txt` is the allowlist used by Kkomantle candidate selection.

- One word per line
- Lines starting with `#` are ignored
- Only words present in the loaded Word2Vec vocabulary are used
- Additional in-code cleanup filters still apply

Environment variables:

- `KKOMANTLE_WHITELIST_PATH` (default: `core/data/kkomantle_whitelist.txt`)
- `KKOMANTLE_MODEL_CANDIDATE_TOPN` (default: `5000`)
- `KKOMANTLE_MOST_SIMILAR_TOPN` (default: `6000`)
- `KKOMANTLE_TOP_WORD_LIMIT` (default: `3000`)

Build from NIKL APIs:

```bash
./venv/bin/python manage.py build_kkomantle_whitelist \
  --source both \
  --candidate-topn 20000 \
  --output core/data/kkomantle_whitelist.txt
```

Supported key env vars:

- `NIKL_API_KEY` (shared key for both APIs)
- `NIKL_OPENDICT_API_KEY`
- `NIKL_STDICT_API_KEY`

The command caches lookup results at `core/data/kkomantle_nikl_cache.json` by default, so you can resume safely.
