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
    text: "textStatus",
    copilot: "copilotStatus",
    summarize: "summarizeStatus",
    caption: "captionStatus",
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
      setStatus("", "video");
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
}

main();

