# gruner_social_features

Backend API for AI-powered social content features (image, video, and text services) built with FastAPI.

## Setup
1. Install dependencies:
   - `pip install -r requirements.txt`
2. Configure environment variables in `.env` (or export in shell).
3. Run the backend:
   - `python main.py`

## API Base
- Local server: `http://localhost:8000`
- Health check: `GET /api/ping`

Success response:
```json
{
  "status": "ok"
}
```

## Environment Variables (Backend Services)

Required by one or more endpoints:
- `HF_TOKEN` - Hugging Face access token (image generation/enhancement/captioning fallback paths)
- `AWS_ACCESS_KEY` - AWS access key
- `AWS_SECRET_KEY` - AWS secret key
- `AWS_REGION` - AWS region for Translate/Polly/Bedrock clients (some services override region internally)
- `BEDROCK_CLAUDE_HAIKU_ID` - Bedrock model id used by text/caption/quote services
- `OPENAI_KEY` - required for OpenAI image model (`gpt-image-1.5`)
- `NOVA_REEL_BUCKET` - S3 URI or bucket name for Nova Reel async output
- `TRANSCRIBE_BUCKET` - S3 bucket used by video-audio translation transcription jobs
- `BEDROCK_CLAUDE_SONNET_ID` - Bedrock Claude Sonnet model id used by voice-to-post/comment cleanup

Optional:
- `TRANSCRIBE_LANGUAGE_CODE` (default: `en-US`)
- `TRANSCRIBE_TIMEOUT_SECONDS` (default: `300`)
- `POLLY_VOICE_ID` (override automatic voice selection)
- `POLLY_ENGINE` (default: `neural`, auto-fallback to `standard` for unsupported voices)
- `POLLY_TRACK_VOLUME_GAIN` (default: `2.4`)
- `QUOTE_CARD_FONT_PATH` (custom font path for quote rendering)
- `AWS_REGION_BEDROCK_IMAGE` (default: `us-west-2`)
- `AWS_REGION_BEDROCK_NOVA_CANVAS` (default: `us-east-1`)
- `AWS_REGION_BEDROCK_NOVA_REEL` (default: `us-east-1`)
- `AWS_REGION_NOVA_REEL_S3` (default: `us-east-1`)

## Error Format
Most failures return FastAPI `HTTPException` with:
```json
{
  "detail": "Error message here"
}
```

Typical status codes:
- `400`: invalid request/body or validation failure
- `500`: provider/runtime/integration error

## Image Services

### 1) List Image Models
**Endpoint:** `GET /api/models`

**Response Body**
```json
{
  "models": [
    "black-forest-labs/FLUX.1-schnell",
    "stabilityai/stable-diffusion-xl-base-1.0",
    "kandinskylab/Kandinsky-5.0-T2I-Lite",
    "amazon.titan-image-generator-v2:0",
    "amazon.nova-canvas-v1:0",
    "gpt-image-1.5"
  ]
}
```

---

### 2) Generate Image
**Endpoint:** `POST /api/generate-image`

**Request Body**
```json
{
  "model": "stabilityai/stable-diffusion-xl-base-1.0",
  "prompt": "cinematic street portrait at night, neon reflections"
}
```

**Response Body**
```json
{
  "model": "stabilityai/stable-diffusion-xl-base-1.0",
  "prompt": "cinematic street portrait at night, neon reflections",
  "mime_type": "image/png",
  "image_base64": "iVBORw0KGgoAAAANSUhEUgAA..."
}
```

Notes:
- `model` must match one of `GET /api/models`.
- Returns PNG as Base64.

---

### 3) Enhance Image
**Endpoint:** `POST /api/enhance-image`

**Request Body**
```json
{
  "image_base64": "iVBORw0KGgoAAAANSUhEUgAA...",
  "mime_type": "image/png",
  "prompt": "slightly warmer tone and improve facial sharpness"
}
```

**Response Body**
```json
{
  "model": "black-forest-labs/FLUX.2-klein-9b-kv",
  "prompt": "Enhance and edit this image: improve lighting ... Additional instructions from the user: slightly warmer tone and improve facial sharpness",
  "mime_type": "image/png",
  "image_base64": "iVBORw0KGgoAAAANSUhEUgAA..."
}
```

Notes:
- `image_base64` required.
- `mime_type` is accepted in request but not currently used in pipeline logic.

---

### 4) Image Captioning (BLIP + style variants)
**Endpoint:** `POST /api/image-captioning`

**Request Body**
```json
{
  "image_base64": "iVBORw0KGgoAAAANSUhEUgAA...",
  "mime_type": "image/png"
}
```

**Response Body**
```json
{
  "blip_caption": "A person walking on a beach at sunset.",
  "captions": {
    "poetic": "The horizon folds into gold as footsteps soften in the sand.",
    "funny": "Proof that cardio is easier when the sky does all the dramatic work.",
    "aesthetic": "Warm dusk tones, soft shoreline texture, and a calm end-of-day mood.",
    "short": "Sunset walk, quiet mind.",
    "deep": "Some journeys are less about distance and more about returning to yourself."
  }
}
```

Notes:
- `image_base64` required.
- Variant captions are generated via Bedrock Claude Haiku.

---

### 5) Chat (Image generation via prompt/messages)
**Endpoint:** `POST /api/chat`

**Request Body**
```json
{
  "model": "black-forest-labs/FLUX.1-schnell",
  "messages": [
    { "role": "system", "content": "You are a creative assistant." },
    { "role": "user", "content": "Generate a dreamy mountain sunrise scene." }
  ],
  "prompt": "optional direct prompt override"
}
```

**Response Body**
```json
{
  "model": "black-forest-labs/FLUX.1-schnell",
  "reply": "Generated an image using black-forest-labs/FLUX.1-schnell.",
  "mime_type": "image/png",
  "image_base64": "iVBORw0KGgoAAAANSUhEUgAA..."
}
```

Notes:
- If `prompt` is present, it can be used as direct input; otherwise prompt is extracted from messages.
- Returns error `400` with `detail: "Missing prompt/messages."` when no usable text is provided.

## Video Services

### 1) List Video Models
**Endpoint:** `GET /api/video-models`

**Response Body**
```json
{
  "models": [
    "amazon.nova-reel-v1:1"
  ]
}
```

---

### 2) Generate Video
**Endpoint:** `POST /api/generate-video`

**Request Body**
```json
{
  "model": "amazon.nova-reel-v1:1",
  "prompt": "aerial cinematic shot over snowy mountains at sunrise"
}
```

**Response Body**
```json
{
  "model": "amazon.nova-reel-v1:1",
  "prompt": "aerial cinematic shot over snowy mountains at sunrise",
  "mime_type": "video/mp4",
  "video_base64": "AAAAIGZ0eXBpc29tAAACAGlzb20..."
}
```

Notes:
- Current supported model list is `VIDEO_MODELS`.
- For Nova Reel, backend starts async Bedrock job and fetches generated `output.mp4` from S3.

---

### 3) Translate Video Audio
**Endpoint:** `POST /api/translate-video-audio`

Pipeline:
1. Extract audio from source video
2. Transcribe via AWS Transcribe (S3-backed)
3. Translate text to target language via AWS Translate
4. Synthesize speech via AWS Polly per segment
5. Re-mux translated track into MP4

**Request Body**
```json
{
  "video_base64": "AAAAIGZ0eXBpc29tAAACAGlzb20...",
  "mime_type": "video/mp4",
  "target_language": "Spanish (es)",
  "keep_original_audio": true
}
```

**Response Body**
```json
{
  "mime_type": "video/mp4",
  "video_base64": "AAAAIGZ0eXBpc29tAAACAGlzb20...",
  "translated_text": "Full target-language transcript of the spoken audio (segment translations joined with spaces)."
}
```

Field details:
- `target_language`: supports language code (`es`), full language name (`Spanish`), or label like `Spanish (es)`.
- `keep_original_audio`: when `true`, output may contain original audio plus translated audio track.
- `translated_text`: concatenation of per-segment translations in processing order (same segments used for Polly).

## Text Services

### 1) Generate Quote Card
**Endpoint:** `POST /api/generate-quote-card`

**Request Body**
```json
{
  "prompt": "resilience after setbacks"
}
```

**Response Body**
```json
{
  "prompt": "resilience after setbacks",
  "quote_text": "You are not behind; you are becoming ready.",
  "mime_type": "image/png",
  "image_base64": "iVBORw0KGgoAAAANSUhEUgAA..."
}
```

Notes:
- Generates quote text (Claude Haiku), background image, then overlays quote into final PNG.

---

### 2) Content Co-Pilot
**Endpoint:** `POST /api/content-copilot`

Modes:
- `generate`: create polished caption from idea in few words (eg. first day at new job, sunrise at mountains, wavy beach)
- `rewrite`: improve/enhance existing caption (eg. Excited to start my new role today!, A peaceful moment to start the day, Keeping it shady in best way possible)
- `ideas`: user gives one domain (eg. mountains, beach, skyscraper) & model return 3-5 caption idea angles

**Request Body**
```json
{
  "mode": "rewrite",
  "text": "launching new app soon maybe stay tuned"
}
```

**Response Body**
```json
{
  "mode": "rewrite",
  "original_text": "launching new app soon maybe stay tuned",
  "result": "We are launching our new app soon. Stay tuned for updates and early access details."
}
```

---

### 3) Summarize Post
**Endpoint:** `POST /api/summarize-post`

**Request Body**
```json
{
  "text": "Long post/article content..."
}
```

**Response Body**
```json
{
  "original_text": "Long post/article content...",
  "result": "- Key point one...\n- Key point two...\n- Key point three..."
}
```

Notes:
- Service prompts model to produce exactly 3-5 concise bullet points.

---

### 4) List Translation Languages
**Endpoint:** `GET /api/translate-languages`

**Response Body**
```json
{
  "languages": [
    { "code": "en", "name": "English" },
    { "code": "es", "name": "Spanish" },
    { "code": "hi", "name": "Hindi" }
  ]
}
```

Notes:
- Language list is sourced from AWS Translate `list_languages`.

---

### 5) Translate Text
**Endpoint:** `POST /api/translate-text`

**Request Body**
```json
{
  "text": "Hello, how are you?",
  "source_language_code": "auto",
  "target_language": "Spanish (es)"
}
```

**Response Body**
```json
{
  "translated_text": "Hola, ¿cómo estás?",
  "source_language_code": "en",
  "target_language_code": "es"
}
```

Field details:
- `source_language_code`: ISO code or `auto`.
- `target_language`: code/name/label format accepted.
- Input text is validated against AWS Translate payload limits.

---

### 6) Voice to Post/Comment
**Endpoint:** `POST /api/voice-to-post-comment`

Pipeline:
1. Accept Base64 encoded audio input
2. Upload source audio to S3 (`TRANSCRIBE_BUCKET`)
3. Run AWS Transcribe (auto language identification by default)
4. Clean and format transcript with Claude Sonnet
5. Return both raw transcript and polished social text

**Request Body**
```json
{
  "audio_base64": "GkXfowEAAAA...",
  "mime_type": "audio/webm",
  "output_kind": "comment",
  "audio_source": "live_microphone"
}
```

**Response Body**
```json
{
  "raw_transcript": "i really loved this post",
  "final_text": "I really loved this post. Thanks for sharing it!",
  "output_kind": "comment",
  "language_code": "auto"
}
```

Field details:
- `output_kind`: `post` or `comment` (defaults to `post`).
- `audio_source`: optional hint for logging/debugging (`live_microphone` or `file_upload`).
- `language_code` in response is `auto` when input language is auto-detected.