#!/usr/bin/env python3
"""Regenerate the Supported Models table in README.md from OpenRouter's live catalog.

The `GET /api/v1/videos/models` endpoint is public (no API key), so this runs
anywhere with outbound HTTPS — locally or in CI. Only the block between the
MODELS_TABLE markers is rewritten; all curated prose (the audio note, the 4K
note) is preserved. Rows are sorted by model id for a deterministic, low-noise
diff.

Usage:
    python scripts/update_models_table.py            # rewrite README.md in place
    python scripts/update_models_table.py --check     # exit 1 if README is stale (CI drift check)

Exit codes: 0 = no change / updated OK; 1 = stale (with --check); 2 = error.
"""
import argparse
import json
import os
import sys
import urllib.request

MODELS_URL = "https://openrouter.ai/api/v1/videos/models"
README = os.path.join(os.path.dirname(__file__), "..", "README.md")
START = "<!-- MODELS_TABLE_START -->"
END = "<!-- MODELS_TABLE_END -->"

# Resolution ranking for "max resolution" selection.
_RES_RANK = {"144p": 1, "240p": 2, "360p": 3, "480p": 4, "540p": 5,
             "720p": 6, "1080p": 7, "1440p": 8, "2k": 8, "4k": 9}


def fetch_models():
    req = urllib.request.Request(MODELS_URL, headers={"User-Agent": "readme-models-sync"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8")).get("data", [])


def max_resolution(res_list):
    if not res_list:
        return "Any"
    best = max(res_list, key=lambda r: _RES_RANK.get(str(r).lower(), 0))
    # Bold 4K to match the existing README emphasis.
    return f"**{best}**" if str(best).lower() == "4k" else str(best)


def fmt_durations(durs):
    """Compress an int list: contiguous -> 'a-bs', two -> 'a or bs', else 'a, b, cs'."""
    if not durs:
        return "Any"
    xs = sorted(int(d) for d in durs)
    if len(xs) == 1:
        return f"{xs[0]}s"
    if xs == list(range(xs[0], xs[-1] + 1)):
        return f"{xs[0]}–{xs[-1]}s"  # en dash
    if len(xs) == 2:
        return f"{xs[0]} or {xs[1]}s"
    return ", ".join(str(x) for x in xs[:-1]) + f", {xs[-1]}s"


def audio_symbol(generate_audio):
    # True = controllable, False = genuinely no audio, null = not controllable.
    if generate_audio is True:
        return "✅"  # ✅
    if generate_audio is False:
        return "❌"  # ❌
    return "➖"      # ➖


def build_table(models):
    lines = [
        "| Model | Max Resolution | Durations | Aspect Ratios | Audio controllable? |",
        "| --- | --- | --- | --- | --- |",
    ]
    for m in sorted(models, key=lambda x: x.get("id", "")):
        ar = m.get("supported_aspect_ratios")
        row = [
            f"`{m['id']}`",
            max_resolution(m.get("supported_resolutions")),
            fmt_durations(m.get("supported_durations")),
            ", ".join(ar) if ar else "Any",
            audio_symbol(m.get("generate_audio")),
        ]
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def splice(readme_text, table):
    if START not in readme_text or END not in readme_text:
        raise SystemExit(f"error: markers {START} / {END} not found in README.md")
    pre, _, rest = readme_text.partition(START)
    _, _, post = rest.partition(END)
    return f"{pre}{START}\n{table}\n{END}{post}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="exit 1 if README is stale; do not write")
    args = ap.parse_args()

    try:
        models = fetch_models()
    except Exception as e:  # noqa: BLE001
        print(f"error fetching catalog: {e}", file=sys.stderr)
        return 2
    if not models:
        print("error: catalog returned no models", file=sys.stderr)
        return 2

    path = os.path.normpath(README)
    with open(path, encoding="utf-8") as f:
        current = f.read()
    updated = splice(current, build_table(models))

    if updated == current:
        print(f"README models table already in sync ({len(models)} models).")
        return 0
    if args.check:
        print(f"README models table is STALE ({len(models)} models live).", file=sys.stderr)
        return 1
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(updated)
    print(f"README models table updated ({len(models)} models).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
