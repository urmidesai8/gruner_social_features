async function loadModels() {
  // Load Image Models
  const res = await fetch("/api/models");
  if (!res.ok) {
    throw new Error(`Failed to load models: ${res.status}`);
  }
  const data = await res.json();
  const models = data.models || [];

  const select = document.getElementById("model");
  select.innerHTML = "";
  const DISABLED_MODELS = ["kandinskylab/Kandinsky-5.0-T2I-Lite", "gpt-image-1.5"];
  let firstEnabledValue = null;
  for (const m of models) {
    const opt = document.createElement("option");
    opt.value = m;
    opt.textContent = m;
    if (DISABLED_MODELS.includes(m)) {
      opt.disabled = true;
      opt.textContent = `${m} (disabled)`;
    } else if (!firstEnabledValue) {
      firstEnabledValue = m;
    }
    select.appendChild(opt);
  }
  // Ensure the dropdown has a selectable value when the first model is disabled.
  if (firstEnabledValue) select.value = firstEnabledValue;

  // Load Video Models
  try {
    const vRes = await fetch("/api/video-models");
    if (vRes.ok) {
      const vData = await vRes.json();
      const vModels = vData.models || [];
      const vSelect = document.getElementById("videoModel");
      if (vSelect) {
        vSelect.innerHTML = "";
        const DISABLED_VIDEO_MODELS = ["Wan-AI/Wan2.2-T2V-A14B-Diffusers"];
        let firstEnabledVideoValue = null;
        for (const m of vModels) {
          const opt = document.createElement("option");
          opt.value = m;
          opt.textContent = m;
          if (DISABLED_VIDEO_MODELS.includes(m)) {
            opt.disabled = true;
            opt.textContent = `${m} (disabled)`;
          } else if (!firstEnabledVideoValue) {
            firstEnabledVideoValue = m;
          }
          vSelect.appendChild(opt);
        }
        if (firstEnabledVideoValue) vSelect.value = firstEnabledVideoValue;
      }
    }
  } catch(e) {
    console.warn("Could not load video models", e);
  }
}

function setStatus(text, type="image") {
  const idByType = {
    image: "status",
    video: "videoStatus",
    videoTranslate: "videoTranslateStatus",
    text: "textStatus",
    copilot: "copilotStatus",
    summarize: "summarizeStatus",
    caption: "captionStatus",
    translate: "translateStatus",
    voicePost: "voicePostStatus",
    hashtag: "hashtagStatus",
  };
  const el = document.getElementById(idByType[type] || "status");
  if (el) el.textContent = text;
}

function setReply(text) {
  document.getElementById("reply").textContent = text;
}

function setImage(data) {
  const img = document.getElementById("image");
  if (!data || !data.image_base64) {
    img.removeAttribute("src");
    return;
  }
  img.src = `data:${data.mime_type};base64,${data.image_base64}`;
}

function setVideo(data) {
  const vid = document.getElementById("videoResult");
  if (!vid) return;
  if (!data || !data.video_base64) {
    vid.removeAttribute("src");
    vid.style.display = 'none';
    return;
  }
  vid.src = `data:${data.mime_type};base64,${data.video_base64}`;
  vid.style.display = 'block';
}

function setQuoteCard(data) {
  const img = document.getElementById("textImage");
  if (!img) return;
  if (!data || !data.image_base64) {
    img.removeAttribute("src");
    img.style.display = "none";
    return;
  }
  img.src = `data:${data.mime_type};base64,${data.image_base64}`;
  img.style.display = "block";
}

function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error("Failed to read selected file."));
    reader.readAsDataURL(file);
  });
}

let voiceMediaRecorder = null;
let voiceMediaStream = null;
let voiceRecordedChunks = [];
let voiceRecordingInProgress = false;

function _stopVoiceStreamTracks() {
  if (voiceMediaStream) {
    for (const track of voiceMediaStream.getTracks()) {
      track.stop();
    }
  }
  voiceMediaStream = null;
}

async function _submitVoiceAudioBase64(audio_base64, mime_type, output_kind) {
  const finalOutput = document.getElementById("voicePostFinalOutput");
  const rawOutput = document.getElementById("voicePostRawTranscript");
  if (finalOutput) finalOutput.value = "";
  if (rawOutput) rawOutput.value = "";
  setStatus("Transcribing and polishing from voice...", "voicePost");

  const res = await fetch("/api/voice-to-post-comment", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      audio_base64,
      mime_type,
      output_kind,
    }),
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data && data.detail ? data.detail : res.statusText;
    throw new Error(detail);
  }

  if (finalOutput && data.final_text) finalOutput.value = data.final_text;
  if (rawOutput && data.raw_transcript) rawOutput.value = data.raw_transcript;
  setStatus("Done.", "voicePost");
}

async function generateVideo() {
  const model = document.getElementById("videoModel").value;
  const prompt = document.getElementById("videoPrompt").value.trim();

  const DISABLED_VIDEO_MODELS = ["Wan-AI/Wan2.2-T2V-A14B-Diffusers"];
  if (DISABLED_VIDEO_MODELS.includes(model)) {
    setStatus("This video model is disabled in the UI.", "video");
    return;
  }

  if (!prompt) {
    setStatus("Please enter a prompt.", "video");
    return;
  }

  setStatus("Generating video...", "video");
  setVideo(null);

  const res = await fetch("/api/generate-video", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: model,
      prompt: prompt,
    }),
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data && data.detail ? data.detail : res.statusText;
    setStatus(`Error: ${detail}`, "video");
    return;
  }

  setStatus("Done.", "video");
  setVideo(data);
}

async function generateQuoteCard() {
  const prompt = document.getElementById("textPrompt").value.trim();
  if (!prompt) {
    setStatus("Please enter a prompt.", "text");
    return;
  }

  setStatus("Generating quote card...", "text");
  setQuoteCard(null);

  const res = await fetch("/api/generate-quote-card", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt }),
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data && data.detail ? data.detail : res.statusText;
    setStatus(`Error: ${detail}`, "text");
    return;
  }

  setStatus("Done.", "text");
  setQuoteCard(data);
}

async function enhanceUploadedImage() {
  const fileInput = document.getElementById("enhanceImageInput");
  const file = fileInput && fileInput.files ? fileInput.files[0] : null;
  if (!file) {
    setStatus("Please upload an image first.", "image");
    return;
  }

  setStatus("Enhancing image...", "image");
  setImage(null);

  const dataUrl = await readFileAsDataUrl(file);
  const enhancePromptEl = document.getElementById("enhancePrompt");
  const enhancePrompt =
    enhancePromptEl && enhancePromptEl.value ? enhancePromptEl.value.trim() : "";
  const res = await fetch("/api/enhance-image", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      image_base64: dataUrl,
      mime_type: file.type || "image/png",
      ...(enhancePrompt ? { prompt: enhancePrompt } : {}),
    }),
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data && data.detail ? data.detail : res.statusText;
    setStatus(`Error: ${detail}`, "image");
    return;
  }

  setStatus("Done.", "image");
  setImage(data);
}

async function generateCaptionOptions() {
  const fileInput = document.getElementById("captionImageInput");
  const file = fileInput && fileInput.files ? fileInput.files[0] : null;
  const output = document.getElementById("captionOptionsOutput");
  if (!file) {
    setStatus("Please choose an image for captioning.", "caption");
    return;
  }

  setStatus("Generating caption options with AI...", "caption");
  if (output) output.value = "";

  const dataUrl = await readFileAsDataUrl(file);
  const res = await fetch("/api/image-captioning", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      image_base64: dataUrl,
      mime_type: file.type || "image/png",
    }),
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data && data.detail ? data.detail : res.statusText;
    setStatus(`Error: ${detail}`, "caption");
    return;
  }

  setStatus("Done.", "caption");
  if (!output) return;

  const captions = data.captions || {};
  const blipCaption = data.blip_caption || "";
  output.value = [
    `BLIP caption: ${blipCaption}`,
    "",
    `poetic: ${captions.poetic || ""}`,
    `funny: ${captions.funny || ""}`,
    `aesthetic: ${captions.aesthetic || ""}`,
    `short: ${captions.short || ""}`,
    `deep: ${captions.deep || ""}`,
  ].join("\n");
}

async function generateCopilot() {
  const mode = document.getElementById("copilotMode").value;
  const text = document.getElementById("copilotInput").value.trim();
  const output = document.getElementById("copilotOutput");

  if (!text) {
    setStatus("Please enter an idea or caption.", "copilot");
    return;
  }

  setStatus("Generating with AI Content Co-Pilot...", "copilot");
  if (output) {
    output.value = "";
  }

  const res = await fetch("/api/content-copilot", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode, text }),
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data && data.detail ? data.detail : res.statusText;
    setStatus(`Error: ${detail}`, "copilot");
    return;
  }

  setStatus("Done.", "copilot");
  if (output && data && data.result) {
    output.value = data.result;
  }
}

async function loadTranslateLanguages() {
  const sourceSel = document.getElementById("translateSourceLang");
  const targetSel = document.getElementById("translateTargetLang");
  const videoTargetSel = document.getElementById("videoTranslateTarget");
  if (!sourceSel || !targetSel) return;

  const res = await fetch("/api/translate-languages");
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data && data.detail ? data.detail : res.statusText;
    setStatus(`Could not load languages: ${detail}`, "translate");
    targetSel.innerHTML = "";
    if (videoTargetSel) {
      videoTargetSel.innerHTML = "";
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "Failed to load — check AWS credentials / region";
      videoTargetSel.appendChild(opt);
    }
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = "Failed to load — check AWS credentials / region";
    targetSel.appendChild(opt);
    return;
  }

  const langs = (data.languages || []).slice();
  langs.sort((a, b) => (a.name || "").localeCompare(b.name || ""));

  const savedSource = sourceSel.value;
  const savedTarget = targetSel.value;

  sourceSel.innerHTML = "";
  const autoOpt = document.createElement("option");
  autoOpt.value = "auto";
  autoOpt.textContent = "Auto-detect";
  sourceSel.appendChild(autoOpt);
  for (const l of langs) {
    const o = document.createElement("option");
    o.value = l.code;
    o.textContent = l.name ? `${l.name} (${l.code})` : l.code;
    sourceSel.appendChild(o);
  }
  if ([...sourceSel.options].some((o) => o.value === savedSource)) {
    sourceSel.value = savedSource;
  }

  targetSel.innerHTML = "";
  for (const l of langs) {
    const o = document.createElement("option");
    o.value = l.code;
    o.textContent = l.name ? `${l.name} (${l.code})` : l.code;
    targetSel.appendChild(o);
  }
  if ([...targetSel.options].some((o) => o.value === savedTarget)) {
    targetSel.value = savedTarget;
  } else if (targetSel.options.length) {
    const prefer = [...targetSel.options].find((o) => o.value === "es")
      || [...targetSel.options].find((o) => o.value === "fr")
      || targetSel.options[0];
    if (prefer) targetSel.value = prefer.value;
  }

  if (videoTargetSel) {
    const savedVideo = videoTargetSel.value;
    videoTargetSel.innerHTML = "";
    for (const l of langs) {
      const o = document.createElement("option");
      // Send label so backend resolver can handle "Name (code)" too.
      o.value = l.name ? `${l.name} (${l.code})` : l.code;
      o.textContent = l.name ? `${l.name} (${l.code})` : l.code;
      videoTargetSel.appendChild(o);
    }
    if ([...videoTargetSel.options].some((o) => o.value === savedVideo)) {
      videoTargetSel.value = savedVideo;
    } else if (videoTargetSel.options.length) {
      const prefer = [...videoTargetSel.options].find((o) => o.textContent.includes("(es)"))
        || [...videoTargetSel.options].find((o) => o.textContent.includes("(fr)"))
        || videoTargetSel.options[0];
      if (prefer) videoTargetSel.value = prefer.value;
    }
  }

  setStatus("", "translate");
}

function setVideoTranslated(data) {
  const vid = document.getElementById("videoTranslateResult");
  const textArea = document.getElementById("videoTranslatedText");
  const textGroup = document.getElementById("videoTranslatedTextGroup");

  if (textArea) textArea.value = "";
  if (textGroup) textGroup.style.display = "none";

  if (!vid) return;
  if (!data || !data.video_base64) {
    vid.removeAttribute("src");
    vid.style.display = "none";
    return;
  }
  vid.src = `data:${data.mime_type};base64,${data.video_base64}`;
  vid.style.display = "block";

  const transcript = data.translated_text != null ? String(data.translated_text).trim() : "";
  if (textArea && transcript) {
    textArea.value = transcript;
    if (textGroup) textGroup.style.display = "block";
  }
}

async function translateVideoAudio() {
  const input = document.getElementById("videoTranslateInput");
  const targetSel = document.getElementById("videoTranslateTarget");
  const keepOriginal = document.getElementById("videoKeepOriginalAudio");

  const file = input && input.files && input.files[0] ? input.files[0] : null;
  if (!file) {
    setStatus("Please choose a video file.", "videoTranslate");
    return;
  }

  const target_language = targetSel ? targetSel.value : "";
  if (!target_language) {
    setStatus("Choose a target language.", "videoTranslate");
    return;
  }

  setStatus("Translating video audio… (this can take a bit)", "videoTranslate");
  setVideoTranslated(null);

  let video_base64;
  try {
    const dataUrl = await readFileAsDataUrl(file);
    const idx = dataUrl.indexOf(",");
    video_base64 = idx >= 0 ? dataUrl.slice(idx + 1) : dataUrl;
  } catch (err) {
    setStatus(`Failed to read video file: ${err.message || err}`, "videoTranslate");
    return;
  }

  const res = await fetch("/api/translate-video-audio", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      video_base64,
      mime_type: file.type || "video/mp4",
      target_language,
      keep_original_audio: keepOriginal ? !!keepOriginal.checked : true,
    }),
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data && data.detail ? data.detail : res.statusText;
    setStatus(`Error: ${detail}`, "videoTranslate");
    return;
  }

  setStatus("Done.", "videoTranslate");
  setVideoTranslated(data);
}

async function translatePost() {
  const input = document.getElementById("translateInput");
  const output = document.getElementById("translateOutput");
  const sourceSel = document.getElementById("translateSourceLang");
  const targetSel = document.getElementById("translateTargetLang");
  const text = input && input.value ? input.value.trim() : "";
  const source_language_code = sourceSel ? sourceSel.value : "auto";
  const target_language = targetSel ? targetSel.value : "";

  if (!text) {
    setStatus("Enter text to translate.", "translate");
    return;
  }
  if (!target_language) {
    setStatus("Choose a target language.", "translate");
    return;
  }

  setStatus("Translating with AWS Translate…", "translate");
  if (output) output.value = "";

  const res = await fetch("/api/translate-text", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      text,
      source_language_code,
      target_language,
    }),
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data && data.detail ? data.detail : res.statusText;
    setStatus(`Error: ${detail}`, "translate");
    return;
  }

  setStatus(
    `Done. (source: ${data.source_language_code || source_language_code} → target: ${data.target_language_code || target_language})`,
    "translate"
  );
  if (output && data.translated_text) {
    output.value = data.translated_text;
  }
}

async function summarizePost() {
  const input = document.getElementById("summarizeInput");
  const output = document.getElementById("summarizeOutput");
  const text = input && input.value ? input.value.trim() : "";

  if (!text) {
    setStatus("Paste some text to summarise.", "summarize");
    return;
  }

  setStatus("Summarising with AI...", "summarize");
  if (output) output.value = "";

  const res = await fetch("/api/summarize-post", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data && data.detail ? data.detail : res.statusText;
    setStatus(`Error: ${detail}`, "summarize");
    return;
  }

  setStatus("Done.", "summarize");
  if (output && data && data.result) {
    output.value = data.result;
  }
}

async function voiceToPostComment() {
  const fileInput = document.getElementById("voicePostAudioInput");
  const kindSel = document.getElementById("voicePostOutputKind");
  const file = fileInput && fileInput.files ? fileInput.files[0] : null;

  if (!file) {
    setStatus("Please choose an audio file.", "voicePost");
    return;
  }

  const output_kind = kindSel ? kindSel.value : "post";

  let audio_base64 = "";
  try {
    const dataUrl = await readFileAsDataUrl(file);
    const idx = dataUrl.indexOf(",");
    audio_base64 = idx >= 0 ? dataUrl.slice(idx + 1) : dataUrl;
  } catch (err) {
    setStatus(`Failed to read audio file: ${err.message || err}`, "voicePost");
    return;
  }

  try {
    await _submitVoiceAudioBase64(audio_base64, file.type || "audio/webm", output_kind);
  } catch (err) {
    setStatus(`Error: ${err.message || err}`, "voicePost");
  }
}

async function toggleLiveVoiceRecording() {
  const liveBtn = document.getElementById("voiceLiveRecordBtn");
  const uploadBtn = document.getElementById("voicePostBtn");
  const fileInput = document.getElementById("voicePostAudioInput");
  const kindSel = document.getElementById("voicePostOutputKind");
  const output_kind = kindSel ? kindSel.value : "post";

  if (!voiceRecordingInProgress) {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setStatus("Live recording is not supported in this browser.", "voicePost");
      return;
    }
    if (typeof MediaRecorder === "undefined") {
      setStatus("MediaRecorder is not available in this browser.", "voicePost");
      return;
    }

    try {
      voiceMediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const preferredMimeType = "audio/webm;codecs=opus";
      const fallbackMimeType = "audio/webm";
      const mimeType = MediaRecorder.isTypeSupported(preferredMimeType)
        ? preferredMimeType
        : (MediaRecorder.isTypeSupported(fallbackMimeType) ? fallbackMimeType : "");
      voiceMediaRecorder = mimeType
        ? new MediaRecorder(voiceMediaStream, { mimeType })
        : new MediaRecorder(voiceMediaStream);
    } catch (err) {
      _stopVoiceStreamTracks();
      setStatus(`Microphone access failed: ${err.message || err}`, "voicePost");
      return;
    }

    voiceRecordedChunks = [];
    voiceMediaRecorder.ondataavailable = (evt) => {
      if (evt.data && evt.data.size > 0) {
        voiceRecordedChunks.push(evt.data);
      }
    };
    voiceMediaRecorder.start(250);
    voiceRecordingInProgress = true;
    if (liveBtn) liveBtn.textContent = "Stop Live Recording";
    if (uploadBtn) uploadBtn.disabled = true;
    if (fileInput) fileInput.disabled = true;
    setStatus("Recording live audio... click stop when done.", "voicePost");
    return;
  }

  if (!voiceMediaRecorder) {
    voiceRecordingInProgress = false;
    if (liveBtn) liveBtn.textContent = "Start Live Recording";
    if (uploadBtn) uploadBtn.disabled = false;
    if (fileInput) fileInput.disabled = false;
    setStatus("Live recorder is not initialized.", "voicePost");
    return;
  }

  const recorder = voiceMediaRecorder;
  const stopPromise = new Promise((resolve) => {
    recorder.onstop = () => resolve();
  });
  recorder.stop();
  await stopPromise;
  voiceRecordingInProgress = false;
  if (liveBtn) liveBtn.textContent = "Start Live Recording";
  if (uploadBtn) uploadBtn.disabled = false;
  if (fileInput) fileInput.disabled = false;
  _stopVoiceStreamTracks();

  const blob = new Blob(voiceRecordedChunks, {
    type: recorder.mimeType || "audio/webm",
  });
  voiceRecordedChunks = [];
  voiceMediaRecorder = null;
  if (!blob.size) {
    setStatus("No audio captured. Please try recording again.", "voicePost");
    return;
  }

  try {
    const dataUrl = await readFileAsDataUrl(blob);
    const idx = dataUrl.indexOf(",");
    const audio_base64 = idx >= 0 ? dataUrl.slice(idx + 1) : dataUrl;
    const finalOutput = document.getElementById("voicePostFinalOutput");
    const rawOutput = document.getElementById("voicePostRawTranscript");
    if (finalOutput) finalOutput.value = "";
    if (rawOutput) rawOutput.value = "";
    setStatus("Transcribing and polishing from live voice...", "voicePost");

    const res = await fetch("/api/voice-to-post-comment", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        audio_base64,
        mime_type: blob.type || "audio/webm",
        output_kind,
        audio_source: "live_microphone",
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail = data && data.detail ? data.detail : res.statusText;
      throw new Error(detail);
    }
    if (finalOutput && data.final_text) finalOutput.value = data.final_text;
    if (rawOutput && data.raw_transcript) rawOutput.value = data.raw_transcript;
    setStatus("Done.", "voicePost");
  } catch (err) {
    setStatus(`Error: ${err.message || err}`, "voicePost");
  }
}

function setHashtagOutputs(data) {
  const hashtagsEl = document.getElementById("hashtagHashtagsOutput");
  const combinedEl = document.getElementById("hashtagCombinedCaptionOutput");
  const usedSourcesEl = document.getElementById("hashtagUsedSourcesOutput");
  const textCaptionEl = document.getElementById("hashtagTextCaptionOutput");
  const imageCaptionEl = document.getElementById("hashtagImageCaptionOutput");
  const videoCaptionEl = document.getElementById("hashtagVideoCaptionOutput");

  const clearAll = () => {
    if (hashtagsEl) hashtagsEl.value = "";
    if (combinedEl) combinedEl.value = "";
    if (usedSourcesEl) usedSourcesEl.value = "";
    if (textCaptionEl) textCaptionEl.value = "";
    if (imageCaptionEl) imageCaptionEl.value = "";
    if (videoCaptionEl) videoCaptionEl.value = "";
  };

  if (!data) {
    clearAll();
    return;
  }

  if (hashtagsEl) hashtagsEl.value = Array.isArray(data.hashtags) ? data.hashtags.join(" ") : "";
  if (combinedEl) combinedEl.value = data.combined_caption ? String(data.combined_caption) : "";
  if (usedSourcesEl) {
    usedSourcesEl.value = Array.isArray(data.used_sources) ? data.used_sources.join(", ") : "";
  }
  if (textCaptionEl) textCaptionEl.value = data.text_caption ? String(data.text_caption) : "";
  if (imageCaptionEl) imageCaptionEl.value = data.image_caption ? String(data.image_caption) : "";
  if (videoCaptionEl) videoCaptionEl.value = data.video_caption ? String(data.video_caption) : "";
}

async function generateHashtags() {
  const textCaptionInput = document.getElementById("hashtagTextCaption");
  const imageInput = document.getElementById("hashtagImageInput");
  const videoInput = document.getElementById("hashtagVideoInput");

  const text_caption = textCaptionInput && textCaptionInput.value ? textCaptionInput.value.trim() : "";
  const imageFile = imageInput && imageInput.files ? imageInput.files[0] : null;
  const videoFile = videoInput && videoInput.files ? videoInput.files[0] : null;
  if (!text_caption && !imageFile && !videoFile) {
    setStatus("Provide at least one of text caption, image, or video.", "hashtag");
    return;
  }

  const payload = { text_caption };
  if (imageFile) {
    payload.media_image = await readFileAsDataUrl(imageFile);
  }
  if (videoFile) {
    payload.media_video = await readFileAsDataUrl(videoFile);
  }

  setStatus("Generating hashtags...", "hashtag");
  setHashtagOutputs(null);

  const res = await fetch("/api/hashtag-generation", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data && data.detail ? data.detail : res.statusText;
    setStatus(`Error: ${detail}`, "hashtag");
    return;
  }

  setHashtagOutputs(data);
  setStatus("Done.", "hashtag");
}

async function generate() {
  const model = document.getElementById("model").value;
  const prompt = document.getElementById("prompt").value.trim();

  const DISABLED_MODELS = ["kandinskylab/Kandinsky-5.0-T2I-Lite", "gpt-image-1.5"];
  if (DISABLED_MODELS.includes(model)) {
    setStatus("This model is disabled in the UI.");
    return;
  }

  if (!prompt) {
    setStatus("Please enter a prompt.");
    return;
  }

  setStatus("Generating...");
  setReply("");
  setImage(null);

  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: model,
      messages: [{ role: "user", content: prompt }],
    }),
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data && data.detail ? data.detail : res.statusText;
    setStatus(`Error: ${detail}`);
    return;
  }

  setStatus("Done.");
  setReply(data.reply || "");
  setImage(data);
}

async function main() {
  try {
    await loadModels();
  } catch (err) {
    setStatus(`Failed to load models: ${err.message || err}`);
  }

  try {
    await loadTranslateLanguages();
  } catch (err) {
    setStatus(`Could not load translation languages: ${err.message || err}`, "translate");
  }

  document.getElementById("generateBtn").addEventListener("click", () => {
    generate().catch((err) => setStatus(`Error: ${err.message || err}`));
  });

  document.getElementById("clearBtn").addEventListener("click", () => {
    document.getElementById("prompt").value = "";
    setReply("");
    setImage(null);
    setStatus("");
  });

  const genVideoBtn = document.getElementById("generateVideoBtn");
  if (genVideoBtn) {
    genVideoBtn.addEventListener("click", () => {
      generateVideo().catch((err) => setStatus(`Error: ${err.message || err}`, "video"));
    });
  }

  const clearVideoBtn = document.getElementById("clearVideoBtn");
  if (clearVideoBtn) {
    clearVideoBtn.addEventListener("click", () => {
      document.getElementById("videoPrompt").value = "";
      setVideo(null);
      setVideoTranslated(null);
      setStatus("", "video");
      setStatus("", "videoTranslate");
    });
  }

  const translateVideoAudioBtn = document.getElementById("translateVideoAudioBtn");
  if (translateVideoAudioBtn) {
    translateVideoAudioBtn.addEventListener("click", () => {
      translateVideoAudio().catch((err) =>
        setStatus(`Error: ${err.message || err}`, "videoTranslate")
      );
    });
  }

  const genTextBtn = document.getElementById("generateTextBtn");
  if (genTextBtn) {
    genTextBtn.addEventListener("click", () => {
      generateQuoteCard().catch((err) => setStatus(`Error: ${err.message || err}`, "text"));
    });
  }

  const clearTextBtn = document.getElementById("clearTextBtn");
  if (clearTextBtn) {
    clearTextBtn.addEventListener("click", () => {
      document.getElementById("textPrompt").value = "";
      setQuoteCard(null);
      setStatus("", "text");
    });
  }

  const genCopilotBtn = document.getElementById("generateCopilotBtn");
  if (genCopilotBtn) {
    genCopilotBtn.addEventListener("click", () => {
      generateCopilot().catch((err) => setStatus(`Error: ${err.message || err}`, "copilot"));
    });
  }

  const clearCopilotBtn = document.getElementById("clearCopilotBtn");
  if (clearCopilotBtn) {
    clearCopilotBtn.addEventListener("click", () => {
      const input = document.getElementById("copilotInput");
      const output = document.getElementById("copilotOutput");
      if (input) input.value = "";
      if (output) output.value = "";
      setStatus("", "copilot");
    });
  }

  const summarizeBtn = document.getElementById("summarizeBtn");
  if (summarizeBtn) {
    summarizeBtn.addEventListener("click", () => {
      summarizePost().catch((err) =>
        setStatus(`Error: ${err.message || err}`, "summarize")
      );
    });
  }

  const clearSummarizeBtn = document.getElementById("clearSummarizeBtn");
  if (clearSummarizeBtn) {
    clearSummarizeBtn.addEventListener("click", () => {
      const input = document.getElementById("summarizeInput");
      const output = document.getElementById("summarizeOutput");
      if (input) input.value = "";
      if (output) output.value = "";
      setStatus("", "summarize");
    });
  }

  const enhanceBtn = document.getElementById("enhanceBtn");
  if (enhanceBtn) {
    enhanceBtn.addEventListener("click", () => {
      enhanceUploadedImage().catch((err) => setStatus(`Error: ${err.message || err}`, "image"));
    });
  }

  const clearEnhanceBtn = document.getElementById("clearEnhanceBtn");
  if (clearEnhanceBtn) {
    clearEnhanceBtn.addEventListener("click", () => {
      const fileInput = document.getElementById("enhanceImageInput");
      if (fileInput) fileInput.value = "";
      const ep = document.getElementById("enhancePrompt");
      if (ep) ep.value = "";
      setStatus("", "image");
    });
  }

  const genCaptionBtn = document.getElementById("generateCaptionOptionsBtn");
  if (genCaptionBtn) {
    genCaptionBtn.addEventListener("click", () => {
      generateCaptionOptions().catch((err) => setStatus(`Error: ${err.message || err}`, "caption"));
    });
  }

  const clearCaptionBtn = document.getElementById("clearCaptionOptionsBtn");
  if (clearCaptionBtn) {
    clearCaptionBtn.addEventListener("click", () => {
      const fileInput = document.getElementById("captionImageInput");
      if (fileInput) fileInput.value = "";
      const output = document.getElementById("captionOptionsOutput");
      if (output) output.value = "";
      setStatus("", "caption");
    });
  }

  const translateBtn = document.getElementById("translateBtn");
  if (translateBtn) {
    translateBtn.addEventListener("click", () => {
      translatePost().catch((err) =>
        setStatus(`Error: ${err.message || err}`, "translate")
      );
    });
  }

  const clearTranslateBtn = document.getElementById("clearTranslateBtn");
  if (clearTranslateBtn) {
    clearTranslateBtn.addEventListener("click", () => {
      const input = document.getElementById("translateInput");
      const output = document.getElementById("translateOutput");
      if (input) input.value = "";
      if (output) output.value = "";
      setStatus("", "translate");
    });
  }

  const voicePostBtn = document.getElementById("voicePostBtn");
  if (voicePostBtn) {
    voicePostBtn.addEventListener("click", () => {
      voiceToPostComment().catch((err) =>
        setStatus(`Error: ${err.message || err}`, "voicePost")
      );
    });
  }

  const clearVoicePostBtn = document.getElementById("clearVoicePostBtn");
  if (clearVoicePostBtn) {
    clearVoicePostBtn.addEventListener("click", () => {
      if (voiceRecordingInProgress && voiceMediaRecorder) {
        voiceMediaRecorder.stop();
      }
      voiceRecordingInProgress = false;
      voiceMediaRecorder = null;
      voiceRecordedChunks = [];
      _stopVoiceStreamTracks();
      const fileInput = document.getElementById("voicePostAudioInput");
      const finalOutput = document.getElementById("voicePostFinalOutput");
      const rawOutput = document.getElementById("voicePostRawTranscript");
      const uploadBtn = document.getElementById("voicePostBtn");
      const liveBtn = document.getElementById("voiceLiveRecordBtn");
      if (fileInput) fileInput.value = "";
      if (fileInput) fileInput.disabled = false;
      if (finalOutput) finalOutput.value = "";
      if (rawOutput) rawOutput.value = "";
      if (uploadBtn) uploadBtn.disabled = false;
      if (liveBtn) liveBtn.textContent = "Start Live Recording";
      setStatus("", "voicePost");
    });
  }

  const liveRecordBtn = document.getElementById("voiceLiveRecordBtn");
  if (liveRecordBtn) {
    liveRecordBtn.addEventListener("click", () => {
      toggleLiveVoiceRecording().catch((err) =>
        setStatus(`Error: ${err.message || err}`, "voicePost")
      );
    });
  }

  const generateHashtagBtn = document.getElementById("generateHashtagBtn");
  if (generateHashtagBtn) {
    generateHashtagBtn.addEventListener("click", () => {
      generateHashtags().catch((err) =>
        setStatus(`Error: ${err.message || err}`, "hashtag")
      );
    });
  }

  const clearHashtagBtn = document.getElementById("clearHashtagBtn");
  if (clearHashtagBtn) {
    clearHashtagBtn.addEventListener("click", () => {
      const textCaptionInput = document.getElementById("hashtagTextCaption");
      const imageInput = document.getElementById("hashtagImageInput");
      const videoInput = document.getElementById("hashtagVideoInput");
      if (textCaptionInput) textCaptionInput.value = "";
      if (imageInput) imageInput.value = "";
      if (videoInput) videoInput.value = "";
      setHashtagOutputs(null);
      setStatus("", "hashtag");
    });
  }
}

main();

