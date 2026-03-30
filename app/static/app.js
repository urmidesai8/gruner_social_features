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
        for (const m of vModels) {
          const opt = document.createElement("option");
          opt.value = m;
          opt.textContent = m;
          vSelect.appendChild(opt);
        }
      }
    }
  } catch(e) {
    console.warn("Could not load video models", e);
  }
}

function setStatus(text, type="image") {
  document.getElementById(type === "image" ? "status" : "videoStatus").textContent = text;
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

async function generateVideo() {
  const model = document.getElementById("videoModel").value;
  const prompt = document.getElementById("videoPrompt").value.trim();

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
}

main();

