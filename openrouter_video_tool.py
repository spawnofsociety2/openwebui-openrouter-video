"""
title: OpenRouter Video Generator
description: Generates high-quality videos using OpenRouter's Video Generation API. Can also list available video models dynamically.
author: Antigravity
version: 1.5
requirements: aiohttp
"""

import os
import uuid
import asyncio
import time
import aiohttp
import json
from typing import Optional, Callable, Awaitable
from urllib.parse import urlparse
from pydantic import BaseModel, Field


def _is_openrouter_url(url: str) -> bool:
    """True only for https URLs whose host is exactly openrouter.ai.

    Parses the host rather than prefix-matching the string: "https://openrouter.ai"
    is also a prefix of "https://openrouter.ai.example.com", so startswith() would
    hand the bearer token to any host that registers such a domain.
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme == "https" and parsed.hostname == "openrouter.ai"


class Tools:
    class Valves(BaseModel):
        OPENROUTER_API_KEY: str = Field(
            default="your-openrouter-api-key", 
            description="Your OpenRouter API Key (get one at openrouter.ai/keys)"
        )
        POLL_INTERVAL_SECONDS: int = Field(
            default=15,
            description="How often to check for video completion (in seconds)"
        )
        MAX_TIMEOUT_SECONDS: int = Field(
            default=600,
            description="Maximum time to wait before failing (in seconds)"
        )
        # Per-request ceiling, so a single hung poll or download can't stall the
        # whole call until MAX_TIMEOUT_SECONDS. Raise it on slow connections.
        REQUEST_TIMEOUT_SECONDS: int = Field(
            default=300,
            description="Maximum time for any single HTTP request, e.g. a video download (in seconds)"
        )

    def __init__(self):
        self.valves = self.Valves()

    async def list_video_models(
        self,
        __event_emitter__: Callable[[dict], Awaitable[None]] = None,
    ) -> str:
        """
        Fetches the live list of available OpenRouter video models, including their supported aspect ratios, durations, resolutions, and features.
        Use this tool when the user asks what video models are available, or if you need to check which models support specific parameters.
        """
        if not self.valves.OPENROUTER_API_KEY or self.valves.OPENROUTER_API_KEY == "your-openrouter-api-key":
            return "Error: Please tell the user to set their OPENROUTER_API_KEY in the tool settings."

        if __event_emitter__:
            await __event_emitter__({
                "type": "status",
                "data": {"description": "Fetching live video models from OpenRouter...", "done": False}
            })

        headers = {
            "Authorization": f"Bearer {self.valves.OPENROUTER_API_KEY}",
            "HTTP-Referer": "https://openwebui.com",
            "X-Title": "OpenWebUI Video Tool"
        }

        timeout = aiohttp.ClientTimeout(total=self.valves.REQUEST_TIMEOUT_SECONDS)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get("https://openrouter.ai/api/v1/videos/models", headers=headers) as resp:
                if resp.status != 200:
                    err_text = await resp.text()
                    return f"API Error {resp.status} when fetching models: {err_text}"
                
                data = await resp.json()
                models = data.get("data", [])

        output = "Available OpenRouter Video Models:\n\n"
        for m in models:
            ar_list = m.get("supported_aspect_ratios")
            dur_list = m.get("supported_durations")
            res_list = m.get("supported_resolutions")
            frames_list = m.get("supported_frame_images")
            pass_list = m.get("allowed_passthrough_parameters")

            ar = ", ".join(ar_list) if ar_list else "Any"
            dur = ", ".join([str(d) for d in dur_list]) if dur_list else "Any"
            res = ", ".join(res_list) if res_list else "Any"
            audio = m.get("generate_audio", False)
            frames = ", ".join(frames_list) if frames_list else "None"
            passthrough = ", ".join(pass_list) if pass_list else "None"
            
            output += f"- Model ID: `{m['id']}`\n"
            output += f"  - Aspect Ratios: {ar}\n"
            output += f"  - Durations (s): {dur}\n"
            output += f"  - Resolutions: {res}\n"
            output += f"  - Supports Audio: {audio}\n"
            output += f"  - Supported Frame Images: {frames}\n"
            output += f"  - Allowed Passthrough Parameters: {passthrough}\n\n"

        return output

    async def generate_video(
        self,
        prompt: str,
        model_id: str = Field(
            # Examples must be slugs that exist in the live catalog; the LLM copies them verbatim.
            description="The ID of the OpenRouter video model to use (e.g., 'google/veo-3.1', 'openai/sora-2-pro', 'kwaivgi/kling-v3.0-pro')."
        ),
        aspect_ratio: str = Field(
            default="16:9", description="Aspect ratio of the video (e.g., '16:9', '9:16'). Must be supported by the model."
        ),
        duration_seconds: str = Field(
            default="", description="(Optional) Length of the generated video in seconds (e.g., '4', '8')."
        ),
        resolution: str = Field(
            default="", description="(Optional) Output resolution (e.g., '720p', '1080p')."
        ),
        generate_audio: bool = Field(
            default=False, description="Set to True to generate audio if the model supports it."
        ),
        image_mode: str = Field(
            default="first_frame", 
            description="If images are provided, how should they be used? Options: 'first_frame', 'last_frame', or 'reference' (for style/character consistency without forcing exact frame composition)."
        ),
        image_urls: list[str] = Field(
            default=None, 
            description="List of public image URLs to use as frames or references. Optional."
        ),
        provider_options: dict = Field(
            default=None, 
            description="Dictionary of provider-specific options. E.g., {'google-vertex': {'parameters': {'negativePrompt': 'blurry'}}}. Check allowed passthrough parameters from list_video_models."
        ),
        __messages__: list = None,
        __event_emitter__: Callable[[dict], Awaitable[None]] = None,
    ) -> str | tuple:
        """
        Generates a video based on the user's prompt and requested model settings using OpenRouter.

        :param prompt: A detailed description of the video you want the model to generate.
        :param model_id: The OpenRouter model ID to use, e.g. 'google/veo-3.1', 'openai/sora-2-pro', 'kwaivgi/kling-v3.0-pro'. Call list_video_models first to see the live catalog.
        :param aspect_ratio: Aspect ratio of the video, e.g. '16:9' or '9:16'. Must be supported by the model. Defaults to '16:9'.
        :param duration_seconds: (Optional) Length of the video in seconds, e.g. '4' or '8'. Must be one the model supports.
        :param resolution: (Optional) Output resolution, e.g. '720p' or '1080p'. Must be one the model supports.
        :param generate_audio: Whether to generate audio. Only some models support audio - check list_video_models. Defaults to False.
        :param image_mode: How to use provided images: 'first_frame', 'last_frame', or 'reference' (style/character consistency without forcing exact frame composition). Defaults to 'first_frame'.
        :param image_urls: (Optional) List of public image URLs to use as frames or references. At most 2 are used for frame anchoring; the second anchors the opposite end.
        :param provider_options: (Optional) Provider-specific options keyed by provider slug, e.g. {'google-vertex': {'parameters': {'negativePrompt': 'blurry'}}}. Check allowed_passthrough_parameters from list_video_models first.
        :return: On success, an (HTMLResponse, message) tuple embedding an HTML5 video player. On failure, an error string.
        """
        # The :param lines above are the ONLY parameter descriptions the LLM sees. OpenWebUI
        # builds the tool schema from this docstring (convert_function_to_pydantic_model) and
        # passes the signature's Field() objects through as default values, not as schema --
        # hence resolve_val below. Keep the Field descriptions in sync for human readers, but
        # anything the model needs to know must live in a :param line, one line each. Text
        # above the first :param becomes the tool description, so keep notes like this out of it.
        def resolve_val(v, default):
            if type(v).__name__ == "FieldInfo":
                d = getattr(v, "default", default)
                if type(d).__name__ in ["PydanticUndefinedType", "ellipsis"] or d is Ellipsis:
                    return default
                return d
            return v

        model_id = resolve_val(model_id, "")
        aspect_ratio = resolve_val(aspect_ratio, "16:9")
        duration_seconds = resolve_val(duration_seconds, "")
        resolution = resolve_val(resolution, "")
        generate_audio = resolve_val(generate_audio, False)
        image_mode = resolve_val(image_mode, "first_frame")
        image_urls = resolve_val(image_urls, None)
        provider_options = resolve_val(provider_options, None)

        try:
            if not self.valves.OPENROUTER_API_KEY or self.valves.OPENROUTER_API_KEY == "your-openrouter-api-key":
                return "Error: Please tell the user to set their OPENROUTER_API_KEY in the tool settings."

            headers = {
                "Authorization": f"Bearer {self.valves.OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://openwebui.com",
                "X-Title": "OpenWebUI Video Tool"
            }

            payload = {
                "model": model_id,
                "prompt": prompt
            }
            if aspect_ratio:
                payload["aspect_ratio"] = aspect_ratio
            if duration_seconds:
                # Tolerate "8s" / "8 seconds" as well as "8"; skip if no digits at all.
                digits = "".join(c for c in str(duration_seconds) if c.isdigit())
                if digits:
                    payload["duration"] = int(digits)
            if resolution:
                payload["resolution"] = resolution
            # Always send the explicit boolean: models that default audio-on (Veo, Sora,
            # Kling, Seedance, Wan) can only be silenced by an explicit false.
            payload["generate_audio"] = bool(generate_audio)

            if provider_options and isinstance(provider_options, dict):
                payload["provider"] = {
                    "options": provider_options
                }

            # Gather images from URLs and User Uploads
            image_list = []
            if image_urls and isinstance(image_urls, list):
                image_list.extend(image_urls)

            if __messages__:
                last_msg = __messages__[-1]
                if isinstance(last_msg, dict) and last_msg.get('role') == 'user':
                    images = last_msg.get('images', [])
                    for uri in images:
                        if isinstance(uri, str) and uri.startswith('data:image'):
                            image_list.append(uri)

            if image_list:
                if __event_emitter__:
                    await __event_emitter__({
                        "type": "status",
                        "data": {"description": f"Processing {len(image_list)} attached image(s)...", "done": False}
                    })

                if image_mode == "reference":
                    payload["input_references"] = [
                        {
                            "type": "image_url",
                            "image_url": {"url": img}
                        } for img in image_list
                    ]
                else:
                    # image_mode names what the FIRST image anchors; a 2nd image takes the
                    # opposite end. Explicit order beats the old positional special-casing.
                    frame_images = []
                    if image_mode == "last_frame":
                        order = ["last_frame", "first_frame"]
                    else:  # "first_frame" (default)
                        order = ["first_frame", "last_frame"]
                    for i, img in enumerate(image_list[:2]):  # exact-frame anchoring supports max 2
                        frame_images.append({
                            "type": "image_url",
                            "image_url": {"url": img},
                            "frame_type": order[i]
                        })
                    payload["frame_images"] = frame_images

            # 1. Submit the Job
            if __event_emitter__:
                await __event_emitter__({
                    "type": "status",
                    "data": {"description": f"Submitting job to {model_id}...", "done": False}
                })

            # One session for submit + poll + download, with a per-request timeout so a
            # hung call fails on its own rather than riding the MAX_TIMEOUT_SECONDS guard.
            timeout = aiohttp.ClientTimeout(total=self.valves.REQUEST_TIMEOUT_SECONDS)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post("https://openrouter.ai/api/v1/videos", headers=headers, json=payload) as resp:
                    if resp.status not in [200, 201, 202]:
                        err_text = await resp.text()
                        return f"API Error {resp.status} when submitting video: {err_text}. You may have used unsupported parameters. Use list_video_models to check the model's capabilities."

                    data = await resp.json()
                    polling_url = data.get("polling_url")
                    job_id = data.get("id")  # needed to build the /content download URL below

                    if not polling_url:
                        return "Error: No polling URL returned by OpenRouter."

                # 2. Poll for Completion
                start_time = time.time()
                video_urls = []

                while True:
                    elapsed_time = int(time.time() - start_time)
                    if elapsed_time > self.valves.MAX_TIMEOUT_SECONDS:
                        return f"Generation timed out after {self.valves.MAX_TIMEOUT_SECONDS} seconds."

                    if __event_emitter__:
                        await __event_emitter__({
                            "type": "status",
                            "data": {"description": f"Generating video... (Elapsed: {elapsed_time}s).", "done": False}
                        })

                    await asyncio.sleep(self.valves.POLL_INTERVAL_SECONDS)

                    async with session.get(polling_url, headers=headers) as poll_resp:
                        if poll_resp.status not in [200, 201, 202]:
                            err_text = await poll_resp.text()
                            return f"Polling API Error {poll_resp.status}: {err_text}"

                        poll_data = await poll_resp.json()
                        status = poll_data.get("status")

                        if status == "completed":
                            urls = poll_data.get("unsigned_urls", [])
                            if not urls and job_id:
                                # unsigned_urls is the fallback and only appears when
                                # has_unsigned_urls is true; /content is the canonical path.
                                urls = [f"https://openrouter.ai/api/v1/videos/{job_id}/content?index=0"]
                            if urls:
                                video_urls = urls
                            break
                        elif status in ["failed", "cancelled", "expired"]:
                            err_msg = poll_data.get("error", "Unknown error")
                            return f"Generation failed: {err_msg}"

                if not video_urls:
                    return "The model completed the request but no video URLs were returned."

                # 3. Download the Video
                if __event_emitter__:
                    await __event_emitter__({
                        "type": "status",
                        "data": {"description": "Video generated! Downloading to server...", "done": False}
                    })

                from open_webui.config import STATIC_DIR
                static_videos_dir = os.path.join(STATIC_DIR, "videos")
                os.makedirs(static_videos_dir, exist_ok=True)

                local_urls = []
                for remote_url in video_urls:
                    video_id = str(uuid.uuid4())
                    file_path = os.path.join(static_videos_dir, f"{video_id}.mp4")

                    # Send the bearer token only to OpenRouter itself: a provider may return a
                    # third-party CDN URL, and that host must never see the API key.
                    dl_headers = headers if _is_openrouter_url(remote_url) else {}
                    async with session.get(remote_url, headers=dl_headers) as dl_resp:
                        if dl_resp.status == 200:
                            video_bytes = await dl_resp.read()
                            with open(file_path, "wb") as f:
                                f.write(video_bytes)
                            local_urls.append(f"/static/videos/{video_id}.mp4")
                        else:
                            return f"Failed to download video from {remote_url}"

            if __event_emitter__:
                await __event_emitter__({
                    "type": "status",
                    "data": {"description": "Videos successfully loaded!", "done": True}
                })

            # 4. Generate HTML Embed
            from fastapi.responses import HTMLResponse
            
            css_aspect = aspect_ratio.replace(":", "/") if aspect_ratio else "16/9"
            
            video_elements = ""
            for url in local_urls:
                video_elements += f'''
                <div style="margin-bottom:1.5rem;">
                  <video controls autoplay loop style="width:100%;aspect-ratio:{css_aspect};background:#000;border-radius:8px;box-shadow:0 4px 15px rgba(0,0,0,0.3);">
                    <source src="{url}" type="video/mp4">
                    Your browser does not support the video tag.
                  </video>
                  <a href="{url}" target="_blank" style="display:block;margin-top:8px;font-family:sans-serif;font-size:0.9em;color:#888;text-align:center;text-decoration:none;">↓ Download Video</a>
                </div>
                '''

            video_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
            <style>
              body, html {{ margin: 0; padding: 0; overflow: hidden; background: transparent; }}
            </style>
            </head>
            <body>
            <div style="width:100%;max-width:1000px;margin:0 auto;margin-bottom:1rem;">
              {video_elements}
            </div>
            <script>
              function reportHeight() {{
                const h = document.documentElement.scrollHeight;
                parent.postMessage({{ type: 'iframe:height', height: h }}, '*');
              }}
              window.addEventListener('load', reportHeight);
              new ResizeObserver(reportHeight).observe(document.body);
            </script>
            </body>
            </html>
            """.strip()

            plural = "s" if len(local_urls) > 1 else ""
            return (
                HTMLResponse(
                    content=video_html,
                    media_type="text/html",
                    headers={"content-disposition": "inline"}
                ),
                f"Generated {len(local_urls)} video{plural} and natively embedded in the chat! Tell the user to enjoy."
            )

        except Exception as e:
            if __event_emitter__:
                await __event_emitter__({
                    "type": "status",
                    "data": {"description": f"Error: {str(e)}", "done": True}
                })
            return f"Failed to generate video: {str(e)}"
