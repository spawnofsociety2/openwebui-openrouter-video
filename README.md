# OpenRouter Video Generator Tool for OpenWebUI

![OpenWebUI OpenRouter Video Gen](https://github.com/spawnofsociety2/openwebui-openrouter-video/raw/master/assets/openwebui_openrouter_videogen.jpg)

A fully autonomous, "agentic" video generation tool for [OpenWebUI](https://openwebui.com/) powered by [OpenRouter](https://openrouter.ai/). This tool empowers your LLM assistant to dynamically discover available video models, submit generation jobs, securely poll for completion, and directly embed the resulting HD videos inside your OpenWebUI chat stream.

## 🚀 Features

- **Agentic Model Discovery:** The LLM can dynamically pull the live catalog of OpenRouter's video models (Sora, Veo, Kling, Seedance, Hailuo, Wan, Grok, etc.) and check their capabilities (supported resolutions, aspect ratios, max durations, audio support) in real time.
- **Background Polling & Auto-Download:** Handles OpenRouter's asynchronous polling endpoints autonomously. Downloads completed `.mp4` assets to your local OpenWebUI static server to prevent broken links or expired signed URLs.
- **Rich HTML5 Embedding:** Injects a beautiful, responsive HTML5 video player natively inside the chat interface with a direct download link.
- **Advanced Model Features:** Supports audio generation toggling, image references for style consistency, and provider-specific passthrough options (e.g. `negativePrompt` for the Google models).

## 🎬 Supported Models

The tool reads OpenRouter's catalog **live** at request time, so this list is a snapshot — new models appear automatically as OpenRouter adds them, and your assistant will always report the current lineup. As of this writing:

| Model | Max Resolution | Durations | Aspect Ratios | Audio |
| --- | --- | --- | --- | --- |
| `openai/sora-2-pro` | 1080p | 4, 8, 12, 16, 20s | 16:9, 9:16 | ✅ |
| `google/veo-3.1` | **4K** | 4, 6, 8s | 16:9, 9:16 | ✅ |
| `google/veo-3.1-fast` | **4K** | 4, 6, 8s | 16:9, 9:16 | ✅ |
| `google/veo-3.1-lite` | 1080p | 4, 6, 8s | 16:9, 9:16 | ✅ |
| `kwaivgi/kling-v3.0-pro` | 720p | 3–15s | 16:9, 9:16, 1:1 | ✅ |
| `kwaivgi/kling-v3.0-std` | 720p | 3–15s | 16:9, 9:16, 1:1 | ✅ |
| `kwaivgi/kling-video-o1` | 720p | 5 or 10s | 16:9, 9:16, 1:1 | ✅ |
| `bytedance/seedance-2.0` | **4K** | 4–15s | 1:1, 3:4, 9:16, 4:3, 16:9, 21:9, 9:21 | ✅ |
| `bytedance/seedance-2.0-fast` | 720p | 4–15s | 1:1, 3:4, 9:16, 4:3, 16:9, 21:9, 9:21 | ✅ |
| `bytedance/seedance-1-5-pro` | 1080p | 4–12s | 1:1, 3:4, 9:16, 9:21, 4:3, 16:9, 21:9 | ✅ |
| `alibaba/wan-2.7` | 1080p | 2–10s | 16:9, 9:16, 1:1, 4:3, 3:4 | ✅ |
| `alibaba/wan-2.6` | 1080p | 5 or 10s | 16:9, 9:16 | ✅ |
| `alibaba/happyhorse-1.1` | 1080p | 3–15s | 16:9, 9:16, 1:1, 4:3, 3:4, 21:9, 9:21 | ❌ |
| `alibaba/happyhorse-1.0` | 1080p | 3–15s | 16:9, 9:16, 1:1, 4:3, 3:4, 21:9, 9:21 | ❌ |
| `minimax/hailuo-2.3` | 1080p | 6 or 10s | 16:9 | ❌ |
| `x-ai/grok-imagine-video` | 720p | 1–15s | 16:9, 9:16, 1:1, 4:3, 3:4, 3:2, 2:3 | ❌ |

> **Note on audio:** Most models generate audio, but `grok-imagine-video`, `hailuo-2.3`, and the `happyhorse` models are video-only. The tool checks this automatically, so if you request audio from a video-only model your assistant will tell you and suggest an alternative.
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

## 📜 License

MIT License. Feel free to fork and modify!
