# OpenRouter Video Generator Tool for OpenWebUI

![OpenWebUI OpenRouter Video Gen](https://github.com/spawnofsociety2/openwebui-openrouter-video/raw/master/assets/openwebui_openrouter_videogen.jpg)

A fully autonomous, "agentic" video generation tool for [OpenWebUI](https://openwebui.com/) powered by [OpenRouter](https://openrouter.ai/). This tool empowers your LLM assistant to dynamically discover available video models, submit generation jobs, securely poll for completion, and directly embed the resulting HD videos inside your OpenWebUI chat stream.

## 🚀 Features

- **Agentic Model Discovery:** The LLM can dynamically pull the live catalog of OpenRouter's video models (Sora, Veo, Kling, Seedance, Hailuo, Wan, Grok, etc.) and check their capabilities (supported resolutions, aspect ratios, max durations, audio support) in real time.
- **Background Polling & Auto-Download:** Handles OpenRouter's asynchronous polling endpoints autonomously. Downloads completed `.mp4` assets to your local OpenWebUI static server to prevent broken links or expired signed URLs.
- **Rich HTML5 Embedding:** Injects a beautiful, responsive HTML5 video player natively inside the chat interface with a direct download link.
- **Advanced Model Features:** Supports audio generation toggling, deterministic seeds, image references for style consistency, and provider-specific passthrough options (e.g. `negativePrompt` for the Google models).
- **Cost-Aware:** The live model catalog includes each model's raw pricing SKUs, so your assistant can answer "use the cheapest model" (units vary by provider — compare within a provider's own units).

## 🎬 Supported Models

The tool reads OpenRouter's catalog **live** at request time, so this list is a snapshot — new models appear automatically as OpenRouter adds them, and your assistant will always report the current lineup. The table below is regenerated from the live catalog by [`scripts/update_models_table.py`](scripts/update_models_table.py) (run on a schedule via GitHub Actions), so it stays close to reality:

<!-- MODELS_TABLE_START -->
| Model | Max Resolution | Durations | Aspect Ratios | Audio controllable? |
| --- | --- | --- | --- | --- |
| `alibaba/happyhorse-1.0` | 1080p | 3–15s | 16:9, 9:16, 1:1, 4:3, 3:4, 21:9, 9:21 | ➖ |
| `alibaba/happyhorse-1.1` | 1080p | 3–15s | 16:9, 9:16, 1:1, 4:3, 3:4, 21:9, 9:21 | ➖ |
| `alibaba/wan-2.6` | 1080p | 5 or 10s | 16:9, 9:16 | ✅ |
| `alibaba/wan-2.7` | 1080p | 2–10s | 16:9, 9:16, 1:1, 4:3, 3:4 | ✅ |
| `bytedance/seedance-1-5-pro` | 1080p | 4–12s | 1:1, 3:4, 9:16, 9:21, 4:3, 16:9, 21:9 | ✅ |
| `bytedance/seedance-2.0` | **4K** | 4–15s | 1:1, 3:4, 9:16, 4:3, 16:9, 21:9, 9:21 | ✅ |
| `bytedance/seedance-2.0-fast` | 720p | 4–15s | 1:1, 3:4, 9:16, 4:3, 16:9, 21:9, 9:21 | ✅ |
| `google/veo-3.1` | **4K** | 4, 6, 8s | 16:9, 9:16 | ✅ |
| `google/veo-3.1-fast` | **4K** | 4, 6, 8s | 16:9, 9:16 | ✅ |
| `google/veo-3.1-lite` | 1080p | 4, 6, 8s | 16:9, 9:16 | ✅ |
| `kwaivgi/kling-v3.0-pro` | 720p | 3–15s | 16:9, 9:16, 1:1 | ✅ |
| `kwaivgi/kling-v3.0-std` | 720p | 3–15s | 16:9, 9:16, 1:1 | ✅ |
| `kwaivgi/kling-video-o1` | 720p | 5 or 10s | 16:9, 9:16, 1:1 | ✅ |
| `minimax/hailuo-2.3` | 1080p | 6 or 10s | 16:9 | ❌ |
| `openai/sora-2-pro` | 1080p | 4, 8, 12, 16, 20s | 16:9, 9:16 | ✅ |
| `x-ai/grok-imagine-video` | 720p | 1–15s | 16:9, 9:16, 1:1, 4:3, 3:4, 3:2, 2:3 | ➖ |
| `x-ai/grok-imagine-video-1.5` | 1080p | 1–15s | Any | ➖ |
<!-- MODELS_TABLE_END -->

> **Note on audio:** The column above means *"is audio controllable via the `generate_audio` parameter"*, not *"does this model have sound"*. The catalog reports three distinct states:
>
> - **✅ controllable** — `generate_audio` is honored. `generate_audio=false` produces a genuinely silent video (verified on `veo-3.1-fast` with ffprobe).
> - **❌ no audio** — only `minimax/hailuo-2.3`, which reports `generate_audio: false` outright.
> - **➖ not controllable** — `grok-imagine-video` and the `happyhorse` models report `generate_audio: null`. They **ignore** the parameter and apply their own default, and that default is *not* necessarily silence: Grok returns a stereo AAC track even when sent `generate_audio: false` (verified with ffprobe).
>
> So if you need a guaranteed-silent result, pick a ✅ model and pass `generate_audio=false`, or strip the audio track yourself afterwards.
>
> **Default behavior (since v1.6):** if you don't mention audio, the tool omits the parameter entirely and the model's own default applies — ✅ models typically produce audio (which may cost more, e.g. Kling bills 0.168/s with audio vs 0.112/s without). v1.5 sent an explicit `false` by default, which silently muted models you never asked to mute.
>
> **Note on 4K:** Only `veo-3.1`, `veo-3.1-fast`, and `seedance-2.0` currently support 4K output.

## 📦 Installation

1. Open your OpenWebUI instance.
2. Navigate to **Workspace** -> **Tools**.
3. Click **+ Add Tool**.
4. Give it a name (e.g., `OpenRouter Video`).
5. Copy the entire contents of [`openrouter_video_tool.py`](https://github.com/spawnofsociety2/openwebui-openrouter-video/blob/master/openrouter_video_tool.py) and paste it into the code editor.
6. Click **Save**.

## ⚙️ Configuration

Once installed, you must provide your OpenRouter API key:

1. Go to the tool's settings (the small equalizer icon next to the tool name, or inside the tool configuration page under Valves).
2. Set your `OPENROUTER_API_KEY`. Get one at [openrouter.ai/keys](https://openrouter.ai/keys).
3. Ensure the tool is **Enabled** in your chat window.

Optional valves: `POLL_INTERVAL_SECONDS` (how often to check for completion), `MAX_TIMEOUT_SECONDS` (overall wait before giving up), and `REQUEST_TIMEOUT_SECONDS` (ceiling for any single HTTP request — raise it if you're on a slow connection and large downloads time out).

> **Note on disk usage:** Generated videos are downloaded to `{STATIC_DIR}/videos/` and are **never cleaned up automatically**. On a long-lived self-hosted instance this directory grows without bound, so if you generate often, prune it periodically (e.g. a scheduled job deleting `.mp4` files older than N days).

## 🗣️ Usage Examples

Because this tool is entirely LLM-driven, you don't need to fiddle with drop-down menus before generating. Just ask your assistant naturally!

**Ask about available models:**
> "What video models can I use right now, and which ones support audio?"

**Generate a video with specific constraints:**
> "Use Grok to generate a 5-second video of a fluffy ginger cat watching the rain. Aspect ratio 16:9."

**Generate at 4K:**
> "Use Veo 3.1 to make an 8-second 4K cinematic drone shot over a misty mountain range."

**Provide styling references:**
> "Make a cinematic panning shot of a cyberpunk city. I've attached an image to use as a style reference, but don't use it as the exact first frame."

## 🛠️ Requirements

- `aiohttp` (Automatically parsed by OpenWebUI)
- An active OpenWebUI instance.

## 🧪 Tests

```bash
python -m unittest discover -s tests -v
```

No network, API key, or OpenWebUI install required — `aiohttp` is mocked and the two runtime imports are stubbed. The suite guards the bugs that were live in 1.4 and cost real money to find: the API key being sent to non-OpenRouter download hosts, completed jobs being dropped when they return no `unsigned_urls`, and `generate_audio=false` never reaching the API. If you change the download loop or the payload builder, run these first.

## 📜 License

MIT License. Feel free to fork and modify!
