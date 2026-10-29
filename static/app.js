"use strict";

const $ = (id) => document.getElementById(id);
const state = {
  documents: [],
  selected: new Set(),
  busy: false,
  health: null,
  toastTimer: null,
};

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

async function api(path, options = {}) {
  let response;
  try {
    response = await fetch(path, {
      ...options,
      signal: AbortSignal.timeout(180000),
    });
  } catch (error) {
    throw new Error(
      error.name === "TimeoutError"
        ? "The request timed out. Indexing may still be running; refresh before uploading again."
        : "Cannot reach the server. Check that the app is running, then retry.",
    );
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail =
      typeof body.detail === "string"
        ? body.detail
        : "The request was invalid. Check your input and retry.";
    throw new Error(detail);
  }
  return response.status === 204 ? null : response.json();
}

function toast(message) {
  clearTimeout(state.toastTimer);
  $("toast").textContent = message;
  $("toast").hidden = false;
  state.toastTimer = setTimeout(() => {
    $("toast").hidden = true;
  }, 6500);
}

function setBusy(busy) {
  state.busy = busy;
  for (const id of ["demo-button", "new-chat", "add-document", "file-input", "retrieval-limit"])
    $(id).disabled = busy;
  document
    .querySelectorAll(".document-row input, .delete-document, .suggestion")
    .forEach((node) => {
      node.disabled = busy;
    });
  $("question").disabled = busy;
  $("upload-zone").setAttribute("aria-disabled", String(busy));
  $("upload-zone").tabIndex = busy ? -1 : 0;
  updateScope();
}

function updateScope() {
  const count = state.selected.size;
  const chunks = state.documents
    .filter((d) => state.selected.has(d.id))
    .reduce((total, d) => total + d.chunks, 0);
  $("scope-label").textContent = count
    ? `Searching ${count} ${count === 1 ? "document" : "documents"} · ${chunks} indexed passages`
    : state.documents.length
      ? "Select at least one document to search"
      : "Add a PDF or load the sample workspace to begin";
  $("send-button").disabled =
    state.busy || !count || $("question").value.trim().length < 3;
}

async function refreshDocuments() {
  const previous = new Set(state.documents.map((d) => d.id));
  state.documents = await api("/api/documents");
  const available = new Set(state.documents.map((d) => d.id));
  state.selected = new Set(
    [...state.selected].filter((id) => available.has(id)),
  );
  state.documents
    .filter((d) => !previous.has(d.id))
    .forEach((d) => state.selected.add(d.id));
  $("document-list").replaceChildren();
  $("document-count").textContent = state.documents.length;
  $("empty-library").hidden = state.documents.length > 0;
  for (const doc of state.documents) {
    const row = element("div", "document-row");
    const input = element("input");
    input.type = "checkbox";
    input.id = `doc-${doc.id}`;
    input.checked = state.selected.has(doc.id);
    input.disabled = state.busy;
    input.addEventListener("change", () => {
      if (input.checked) state.selected.add(doc.id);
      else state.selected.delete(doc.id);
      updateScope();
    });
    const label = element("label");
    label.htmlFor = input.id;
    label.title = doc.filename;
    label.append(
      element("span", "document-name", doc.filename),
      element(
        "span",
        "document-meta",
        `${doc.pages} pages · ${doc.chunks} passages`,
      ),
    );
    const remove = element("button", "delete-document", "×");
    remove.type = "button";
    remove.disabled = state.busy;
    remove.setAttribute("aria-label", `Remove ${doc.filename}`);
    remove.addEventListener("click", async () => {
      if (
        state.busy ||
        !confirm(
          `Remove ${doc.filename} and its indexed passages from this workspace?`,
        )
      )
        return;
      setBusy(true);
      try {
        await api(`/api/documents/${doc.id}`, { method: "DELETE" });
        await refreshDocuments();
        toast(
          "Document and indexed passages removed. Existing chat text remains until you start a new chat.",
        );
      } catch (error) {
        toast(error.message);
      } finally {
        setBusy(false);
      }
    });
    row.append(input, label, remove);
    $("document-list").append(row);
  }
  updateScope();
}

async function loadDemo() {
  if (state.busy) return false;
  setBusy(true);
  $("upload-status").textContent =
    "Indexing sample PDFs. First use downloads the embedding model; this can take a minute.";
  try {
    await api("/api/demo", { method: "POST" });
    await refreshDocuments();
    $("upload-status").textContent = "Sample documents are ready.";
    toast("Sample workspace loaded. Try a question below.");
    return true;
  } catch (error) {
    $("upload-status").textContent = error.message;
    toast(error.message);
    return false;
  } finally {
    setBusy(false);
  }
}

async function uploadFiles(files) {
  if (state.busy || !files.length) return;
  setBusy(true);
  let succeeded = 0;
  const errors = [];
  try {
    for (const [index, file] of [...files].entries()) {
      if (
        !file.name.toLowerCase().endsWith(".pdf") ||
        file.size > (state.health?.max_file_mb || 10) * 1024 * 1024
      ) {
        errors.push(`${file.name}: choose a PDF under ${state.health?.max_file_mb || 10} MB.`);
        continue;
      }
      $("upload-status").textContent =
        `Indexing ${index + 1} of ${files.length}: ${file.name}. First use may download the embedding model.`;
      const body = new FormData();
      body.append("file", file);
      try {
        const result = await api("/api/documents", { method: "POST", body });
        succeeded += 1;
        if (result.duplicate)
          toast(`${file.name} is already in this workspace.`);
      } catch (error) {
        errors.push(`${file.name}: ${error.message}`);
      }
    }
    await refreshDocuments();
    $("upload-status").textContent = errors.length
      ? errors.join(" ")
      : `${succeeded} ${succeeded === 1 ? "document" : "documents"} ready to search.`;
    if (errors.length) toast(errors.join(" "));
  } catch (error) {
    toast(error.message);
  } finally {
    $("file-input").value = "";
    setBusy(false);
  }
}

function sourceCard(source) {
  const card = element("article", "source-card");
  const meta = element("div", "source-meta");
  meta.append(
    element("span", "source-number", `[${source.number}] SOURCE`),
    element("span", "", `PAGE ${source.page}`),
  );
  const link = element("a", "", "Download original PDF ↗");
  link.href = `/api/documents/${encodeURIComponent(source.document_id)}/file`;
  link.setAttribute("download", "");
  card.append(
    meta,
    element("h3", "", source.filename),
    element("blockquote", "", source.quote),
    link,
    element(
      "p",
      "source-score",
      `Cosine similarity ${source.score.toFixed(3)} · not a confidence score`,
    ),
  );
  return card;
}

function showSources(citations) {
  $("evidence-empty").hidden = citations.length > 0;
  $("evidence-list").replaceChildren(...citations.map(sourceCard));
  if (window.matchMedia("(max-width: 600px)").matches) {
    openDialog("Source evidence", (container) => {
      container.classList.add("source-modal");
      container.append(...citations.map(sourceCard));
    });
  }
}

function message(role, text) {
  const node = element("article", `message ${role}`);
  const label = element(
    "div",
    "message-label",
    role === "user" ? "YOU" : "MARGIN",
  );
  const body = element("div", "message-body", text);
  node.append(label, body);
  $("messages").append(node);
  return node;
}

function scrollChat() {
  $("chat-scroll").scrollTop = $("chat-scroll").scrollHeight;
}

async function askQuestion(question) {
  if (state.busy || state.selected.size === 0 || question.trim().length < 3)
    return;
  const documentIds = [...state.selected];
  const retrievalLimit = Number($("retrieval-limit").value);
  $("welcome").hidden = true;
  setSidebarOpen(false);
  $("question").value = "";
  $("question").rows = 1;
  message("user", question);
  const pending = message("assistant", "Finding relevant passages…");
  pending.classList.add("pending");
  pending.setAttribute("aria-busy", "true");
  setBusy(true);
  scrollChat();
  try {
    const result = await api("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, document_ids: documentIds, retrieval_limit: retrievalLimit }),
    });
    pending.querySelector(".message-body").textContent = result.answer;
    const meta = element("div", "answer-meta");
    const label =
      result.mode === "gemini"
        ? "Gemini · generated answer"
        : "Local · exact source evidence";
    meta.append(
      element("span", "", label),
      element(
        "span",
        "",
        `${(result.elapsed_ms / 1000).toFixed(1)}s · ${result.retrieved} retrieved passages`,
      ),
    );
    if (result.citations.length) {
      const show = element(
        "button",
        "citation-button",
        `View ${result.citations.length} ${result.citations.length === 1 ? "source" : "sources"} ↗`,
      );
      show.type = "button";
      show.addEventListener("click", () => showSources(result.citations));
      meta.append(show);
    }
    pending.append(meta);
    // Keep mobile reading uninterrupted. Open evidence only when explicitly requested.
    $("evidence-empty").hidden = result.citations.length > 0;
    $("evidence-list").replaceChildren(...result.citations.map(sourceCard));
  } catch (error) {
    pending.querySelector(".message-body").textContent = error.message;
    pending.classList.add("error-message");
  } finally {
    pending.classList.remove("pending");
    pending.removeAttribute("aria-busy");
    setBusy(false);
    scrollChat();
    $("question").focus({ preventScroll: true });
  }
}

function openDialog(title, build) {
  $("dialog-title").textContent = title;
  const container = $("dialog-content");
  container.className = "dialog-section";
  container.replaceChildren();
  build(container);
  $("info-dialog").showModal();
}

function section(container, title, text) {
  container.append(element("h3", "", title), element("p", "", text));
}

$("chat-form").addEventListener("submit", (event) => {
  event.preventDefault();
  askQuestion($("question").value.trim());
});
$("question").addEventListener("input", () => {
  $("question").rows = Math.min(
    5,
    Math.max(1, $("question").value.split("\n").length),
  );
  updateScope();
});
$("question").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    $("chat-form").requestSubmit();
  }
});
$("file-input").addEventListener("change", (event) =>
  uploadFiles(event.target.files),
);
$("add-document").addEventListener("click", () => $("file-input").click());
$("upload-zone").addEventListener("keydown", (event) => {
  if ((event.key === "Enter" || event.key === " ") && !state.busy) {
    event.preventDefault();
    $("file-input").click();
  }
});
$("demo-button").addEventListener("click", loadDemo);
$("research-button").addEventListener("click", () => {
  setSidebarOpen(false);
  $("question").focus();
});
for (const name of ["dragenter", "dragover"])
  $("upload-zone").addEventListener(name, (event) => {
    event.preventDefault();
    if (!state.busy) $("upload-zone").classList.add("dragging");
  });
for (const name of ["dragleave", "drop"])
  $("upload-zone").addEventListener(name, (event) => {
    event.preventDefault();
    $("upload-zone").classList.remove("dragging");
    if (name === "drop") uploadFiles(event.dataTransfer.files);
  });
for (const button of document.querySelectorAll(".suggestion"))
  button.addEventListener("click", async () => {
    if (!state.documents.length && !(await loadDemo())) return;
    if (!state.selected.size) {
      toast("Select at least one source document first.");
      return;
    }
    askQuestion(button.dataset.question);
  });
$("new-chat").addEventListener("click", () => {
  if (state.busy) return;
  $("messages").replaceChildren();
  $("welcome").hidden = false;
  $("evidence-list").replaceChildren();
  $("evidence-empty").hidden = false;
  $("question").value = "";
  updateScope();
  $("question").focus({ preventScroll: true });
  $("chat-scroll").scrollTop = 0;
});
const mobileSidebar = window.matchMedia("(max-width: 800px)");
function setSidebarOpen(open) {
  $("sidebar").classList.toggle("open", open);
  $("sidebar").inert = mobileSidebar.matches && !open;
  $("menu-button").setAttribute("aria-expanded", String(open));
}
$("menu-button").addEventListener("click", () =>
  setSidebarOpen(!$("sidebar").classList.contains("open")),
);
mobileSidebar.addEventListener("change", () => setSidebarOpen(false));
document.addEventListener("keydown", (event) => {
  if (
    event.key === "Escape" &&
    !$("info-dialog").open &&
    $("sidebar").classList.contains("open")
  ) {
    setSidebarOpen(false);
    $("menu-button").focus();
  }
});
setSidebarOpen(false);
$("close-dialog").addEventListener("click", () => $("info-dialog").close());
$("settings-button").addEventListener("click", () =>
  openDialog("Model & privacy", (container) => {
    section(
      container,
      "Answer generation",
      state.health?.mode === "gemini"
        ? `Gemini is enabled (${state.health.generation_model}). Relevant passages and your question are sent to Google for each answer.`
        : "Local evidence mode is enabled. No language model is generating answers. To enable Gemini, set GEMINI_API_KEY in the server’s .env file and restart the app.",
    );
    section(
      container,
      "Local semantic retrieval",
      `${state.health?.embedding_model || "BAAI/bge-small-en-v1.5"} runs on the backend server. Hosted deployments bundle the weights during the build. Local installations download them on first use. Cosine similarity measures retrieval relevance, not answer confidence.`,
    );
    section(
      container,
      "Where your data lives",
      (state.health?.storage === "private-blob"
        ? "PDFs and vectors are saved as private SQLite snapshots in Vercel Blob, not on an ephemeral function disk. Hosted workspaces have a 32 MB storage limit. "
        : "PDFs and vectors are stored in SQLite on this server. ") +
      "A private browser cookie identifies your workspace. Losing the cookie loses access; there is no account recovery. Chat text stays in this tab’s memory. Deleting a document removes its stored PDF and vectors, but not existing chat text.",
    );
    section(
      container,
      "Demo boundary",
      "This is a short-lived project demo, not a production document service. Avoid confidential or irreplaceable documents. Gemini receives retrieved passages when enabled. Scanned PDFs need OCR before upload.",
    );
  }),
);
$("guide-button").addEventListener("click", () =>
  openDialog("Project & evaluation", (container) => {
    section(
      container,
      "What this project demonstrates",
      "PDF text extraction, page-preserving overlapping chunks, dense sentence embeddings, a persistent vector store, cosine retrieval, and answers with inspectable page citations. Gemini is optional but required for generated-answer evaluation.",
    );
    section(
      container,
      "The test corpus",
      "The sample workspace contains three fictional PDFs and 24 development questions: 18 supported questions and 6 questions the corpus cannot answer. They are demonstration fixtures, not a held-out benchmark.",
    );
    section(
      container,
      "Run the evaluation",
      "From the project directory, run the command below. Add --gemini to measure generated answers after setting an API key. That sends the fictional sample passages to Google and may use billable quota.",
    );
    container.append(element("code", "", "uv run python -m scripts.evaluate"));
    section(
      container,
      "Submission materials",
      "README.md contains setup instructions. docs/SUBMISSION.md maps the screenshot requirements to the implementation and includes the demo script. evaluation/results.json records the latest local evaluation. Review limitations and add your own documents and questions before submitting.",
    );
  }),
);

async function initialize() {
  try {
    state.health = await api("/api/health");
    document.querySelector(".upload-zone small").textContent = `${state.health.max_file_mb} MB each · up to ${state.health.max_pages} pages`;
    if (state.health.hosted) document.querySelector(".workspace-label span").textContent = "HOSTED";
    $("mode-badge").lastChild.textContent =
      state.health.mode === "gemini"
        ? "Gemini configured"
        : "Local evidence mode";
    $("mode-note").textContent =
      state.health.mode === "gemini"
        ? "Generated answers can be wrong. Check the citations."
        : "Exact passages, not AI-generated answers. Gemini is optional.";
    await refreshDocuments();
  } catch (error) {
    $("mode-badge").lastChild.textContent = "Server unavailable";
    toast(error.message);
  }
}
initialize();
