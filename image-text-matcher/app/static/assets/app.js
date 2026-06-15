const POLL_MS = 10000;
const POLL_HIDDEN_MS = 30000;
const TOAST_MS = 3200;
const IMAGE_SEARCH_DEBOUNCE_MS = 300;
const IMAGE_SEARCH_LIMIT = 30;
const PAGE_SIZE_OPTIONS = [25, 50, 100];
const GOVERNMENT_WARNING =
  "GOVERNMENT WARNING:(1) According to the Surgeon General, women should not drink alcoholic beverages during pregnancy because of the risk of birth defects. (2) Consumption of alcoholic beverages impairs your ability to drive a car or operate machinery, and may cause health problems.";
const CATEGORY_OPTIONS = ["Malt Beverage", "Wine", "Distilled Spirits"];

const state = {
  submissions: [],
  images: [],
  results: [],
  queue: [],
  stats: null,
  selection: { submissions: [], images: [], queue: [] },
  sort: {
    submissions: { key: "created", direction: "desc" },
    images: { key: "modified", direction: "desc" },
    queue: { key: "created", direction: "asc" },
  },
  pagination: {
    submissions: { page: 1, pageSize: 25 },
    images: { page: 1, pageSize: 25 },
    queue: { page: 1, pageSize: 25 },
  },
  filter: { submissions: "", images: "", queue: "" },
  editingSubmissionId: null,
  submissionImagePath: "",
  submissionImageLibraryFilter: "",
  selectedSubmissionResultId: null,
  selectedResultField: null,
  submissionFormDirty: false,
  deferredViews: { submissions: false, images: false, queue: false },
  imageSearchHandle: null,
};

const submissionFields = [
  { name: "category", label: "Category", kind: "select", wide: true, options: CATEGORY_OPTIONS, required: true },
  { name: "brand", label: "Brand", kind: "input", required: true },
  { name: "classType", label: "Class Type", kind: "input", required: true },
  { name: "address", label: "Name/Address of Bottler/Producer", kind: "textarea", wide: true, required: true },
  { name: "netContents", label: "Net Contents", kind: "input", required: true },
  { name: "alcohol", label: "Alcohol", kind: "input", required: false, help: "Optional. If provided, it must match for approval." },
  { name: "origin", label: "Origin", kind: "input", required: false, help: "Optional. If provided, it must match for approval." },
  { name: "appellation", label: "Appellation", kind: "input", showWhenCategory: "Wine", required: false, help: "Optional for wine. If provided, it must match for approval." },
  { name: "warning", label: "Government Warning", kind: "textarea", wide: true, readOnly: true, required: true },
];

const fieldLabels = {
  id: "ID",
  brand: "Brand",
  classType: "Class Type",
  category: "Category",
  address: "Name/Address of Bottler/Producer",
  netContents: "Net Contents",
  alcohol: "Alcohol",
  origin: "Origin",
  appellation: "Appellation",
  warning: "Government Warning",
  images: "Image",
  created: "Created",
  processed: "Processed",
  approved: "Approved",
  name: "Name",
  path: "Path",
  sizeBytes: "Size",
  modified: "Modified",
  submissionId: "Submission",
  status: "Status",
  processStarted: "Started",
  processCompleted: "Completed",
  combinedImage: "Combined Image",
  combinedImageUrl: "Combined Image URL",
  errorMessage: "Error Message",
  updated: "Updated",
};

const dateFields = new Set(["created", "modified", "processed", "processStarted", "processCompleted", "updated", "started", "completed"]);

const tableConfigs = {
  submissions: {
    head: document.getElementById("submission-head"),
    body: document.getElementById("submission-body"),
    details: document.getElementById("submission-details"),
    pagination: document.getElementById("submission-pagination"),
    columns: [
      ["id", "ID"],
      ["brand", "Brand"],
      ["classType", "Class"],
      ["category", "Category"],
      ["approved", "Approved"],
      ["created", "Created"],
    ],
  },
  images: {
    head: document.getElementById("image-head"),
    body: document.getElementById("image-body"),
    details: document.getElementById("image-details"),
    pagination: document.getElementById("image-pagination"),
    columns: [
      ["name", "Name"],
      ["path", "Path"],
      ["sizeBytes", "Size"],
      ["modified", "Modified"],
    ],
  },
  queue: {
    head: document.getElementById("queue-head"),
    body: document.getElementById("queue-body"),
    details: document.getElementById("queue-details"),
    pagination: document.getElementById("queue-pagination"),
    columns: [
      ["id", "ID"],
      ["submissionId", "Submission"],
      ["status", "Status"],
      ["created", "Created"],
      ["updated", "Updated"],
    ],
  },
};

init();

async function init() {
  buildSubmissionForm();
  buildTableHeaders();
  bindEvents();
  const session = await api("/auth/session");
  if (session.authenticated) {
    showDashboard();
    await refreshAll();
    startPolling();
  } else {
    showLogin();
  }
}

function bindEvents() {
  document.getElementById("login-form").addEventListener("submit", onLogin);
  document.getElementById("logout-button").addEventListener("click", onLogout);
  document.getElementById("nav").addEventListener("click", onNavigate);
  document.getElementById("submission-filter").addEventListener("input", (event) => setFilter("submissions", event.target.value));
  document.getElementById("image-filter").addEventListener("input", (event) => setFilter("images", event.target.value));
  document.getElementById("queue-filter").addEventListener("input", (event) => setFilter("queue", event.target.value));
  document.getElementById("submission-refresh").addEventListener("click", refreshAll);
  document.getElementById("image-refresh").addEventListener("click", refreshAll);
  document.getElementById("queue-refresh").addEventListener("click", refreshAll);
  document.getElementById("pause-processing").addEventListener("click", () => updateProcessing("/admin/processing/pause"));
  document.getElementById("resume-processing").addEventListener("click", () => updateProcessing("/admin/processing/resume"));
  document.getElementById("submission-new").addEventListener("click", resetSubmissionForm);
  document.getElementById("submission-edit").addEventListener("click", loadSelectedSubmissionForEdit);
  document.getElementById("submission-queue").addEventListener("click", queueSelectedSubmission);
  document.getElementById("submission-cancel").addEventListener("click", resetSubmissionForm);
  document.getElementById("submission-form").addEventListener("submit", saveSubmission);
  document.getElementById("submission-delete-selected").addEventListener("click", deleteSelectedSubmissions);
  document.getElementById("image-upload-open").addEventListener("click", () => document.getElementById("images-upload-input").click());
  document.getElementById("images-upload-input").addEventListener("change", onImagesLibraryUpload);
  document.getElementById("image-delete-selected").addEventListener("click", deleteSelectedImages);
  document.getElementById("queue-delete-selected").addEventListener("click", deleteSelectedQueueItems);
  document.getElementById("queue-clear").addEventListener("click", clearQueue);
  document.getElementById("submission-form").addEventListener("change", onSubmissionFormChange);
  document.getElementById("submission-form").addEventListener("click", onSubmissionFormClick);
  document.getElementById("submission-form").addEventListener("input", onSubmissionFormInput);
  document.addEventListener("focusout", () => window.setTimeout(flushDeferredViews, 0));
  document.addEventListener("visibilitychange", onVisibilityChange);
}

function buildSubmissionForm() {
  const form = document.getElementById("submission-form");
  form.innerHTML = "";

  submissionFields.forEach((fieldConfig) => {
    const wrapper = document.createElement("label");
    wrapper.className = `${fieldConfig.wide ? "wide " : ""}${fieldConfig.showWhenCategory ? "conditional-field" : ""}`.trim();
    wrapper.dataset.fieldName = fieldConfig.name;
    if (fieldConfig.showWhenCategory) wrapper.dataset.showWhenCategory = fieldConfig.showWhenCategory;
    wrapper.innerHTML = `
      <span class="field-heading">
        <span>${fieldConfig.label}</span>
        <span class="field-badge">${getFieldBadgeText(fieldConfig)}</span>
      </span>
      ${fieldConfig.help ? `<span class="field-help muted">${fieldConfig.help}</span>` : ""}
    `;

    let field;
    if (fieldConfig.kind === "textarea") {
      field = document.createElement("textarea");
      field.className = "form-control";
    } else if (fieldConfig.kind === "select") {
      field = document.createElement("select");
      field.className = "form-select";
      field.innerHTML = fieldConfig.options
        .map((option) => `<option value="${option}">${option}</option>`)
        .join("");
    } else {
      field = document.createElement("input");
      field.type = "text";
      field.className = "form-control";
    }

    field.name = fieldConfig.name;
    field.id = `field-${fieldConfig.name}`;
    if (fieldConfig.readOnly) {
      field.readOnly = true;
      field.value = GOVERNMENT_WARNING;
    }
    wrapper.appendChild(field);
    form.appendChild(wrapper);
  });

  const imageField = document.createElement("div");
  imageField.className = "wide image-manager";
  imageField.innerHTML = `
    <label class="image-input-stack">
      <span>Image</span>
      <div class="image-source-grid">
        <div class="image-source-card">
          <span class="image-source-label">Search</span>
          <div class="image-library-stack">
            <input id="image-library-search" class="form-control" type="search" placeholder="Search image library" />
            <div id="image-library-results" class="image-library-results"></div>
          </div>
        </div>
        <div class="image-source-card">
          <span class="image-source-label">Upload</span>
          <div class="image-input-row">
            <button id="image-upload-trigger" type="button">Upload Image</button>
          </div>
        </div>
      </div>
      <input id="image-upload-input" type="file" accept="image/*" hidden />
    </label>
    <div id="image-selection" class="image-list"></div>
  `;
  form.appendChild(imageField);

  renderImageLibraryPrompt();
  resetSubmissionForm();
}

function buildTableHeaders() {
  Object.entries(tableConfigs).forEach(([view, config]) => {
    const row = document.createElement("tr");
    row.innerHTML = '<th scope="col" class="select-column"></th>';
    config.columns.forEach(([key, label]) => {
      const th = document.createElement("th");
      th.scope = "col";
      th.dataset.sortColumn = key;
      th.innerHTML = `
        <button class="sort-button" type="button" data-view="${view}" data-sort="${key}" title="Sort by ${escapeHtml(label)}">
          <span>${escapeHtml(label)}</span>
          <span class="sort-icon" aria-hidden="true"></span>
          <span class="visually-hidden"></span>
        </button>
      `;
      row.appendChild(th);
    });
    config.head.innerHTML = "";
    config.head.appendChild(row);
    config.head.addEventListener("click", onSort);
    config.pagination.addEventListener("click", onPaginationClick);
    config.pagination.addEventListener("change", onPaginationChange);
  });
}

async function onLogin(event) {
  event.preventDefault();
  const error = document.getElementById("login-error");
  error.hidden = true;
  const username = document.getElementById("username").value;
  const password = document.getElementById("password").value;
  try {
    await api("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    showDashboard();
    await refreshAll();
    startPolling();
  } catch (err) {
    error.textContent = err.message;
    error.hidden = false;
  }
}

async function onLogout() {
  await api("/auth/logout", { method: "POST" });
  stopPolling();
  showLogin();
}

function onNavigate(event) {
  const button = event.target.closest("[data-view]");
  if (!button) return;
  document.querySelectorAll(".nav-link").forEach((node) => node.classList.toggle("active", node === button));
  document.querySelectorAll(".view").forEach((node) => node.classList.toggle("active", node.dataset.panel === button.dataset.view));
  flushDeferredViews();
}

function onSort(event) {
  const button = event.target.closest("[data-sort]");
  if (!button) return;
  const { view, sort: key } = button.dataset;
  const current = state.sort[view];
  state.sort[view] = {
    key,
    direction: current.key === key && current.direction === "asc" ? "desc" : "asc",
  };
  state.pagination[view].page = 1;
  renderTable(view);
}

function onPaginationClick(event) {
  const button = event.target.closest("[data-page]");
  if (!button || button.disabled) return;
  const { view, page } = button.dataset;
  state.pagination[view].page = Number(page);
  renderTable(view);
}

function onPaginationChange(event) {
  if (!event.target.matches("[data-page-size]")) return;
  const { view } = event.target.dataset;
  state.pagination[view].pageSize = Number(event.target.value);
  state.pagination[view].page = 1;
  renderTable(view);
}

function onSubmissionFormChange(event) {
  state.submissionFormDirty = true;

  if (event.target.id === "field-category") {
    syncSubmissionFormVisibility();
  }

  if (event.target.id === "image-upload-input" && event.target.files?.[0]) {
    uploadImage(event.target.files[0]).finally(() => {
      event.target.value = "";
    });
  }
}

function onSubmissionFormInput(event) {
  if (event.target.id === "image-library-search") {
    state.submissionImageLibraryFilter = event.target.value.trim().toLowerCase();
    window.clearTimeout(state.imageSearchHandle);
    state.imageSearchHandle = window.setTimeout(populateImageLibraryOptions, IMAGE_SEARCH_DEBOUNCE_MS);
    return;
  }

  state.submissionFormDirty = true;
}

function onSubmissionFormClick(event) {
  const imageChoice = event.target.closest("[data-image-path]");
  if (imageChoice) {
    state.submissionFormDirty = true;
    setSelectedImagePath(imageChoice.dataset.imagePath || "");
    return;
  }

  if (event.target.id === "image-upload-trigger") {
    document.getElementById("image-upload-input").click();
    return;
  }

  const removeButton = event.target.closest("[data-remove-image]");
  if (removeButton) {
    state.submissionFormDirty = true;
    clearSelectedImage();
  }
}

function setFilter(view, value) {
  state.filter[view] = value.toLowerCase();
  state.pagination[view].page = 1;
  renderTable(view);
}

async function refreshAll() {
  const [stats, submissions, images, results, queue] = await Promise.all([
    api("/admin/dashboard/stats"),
    api("/submissions?limit=500"),
    api("/images"),
    api("/process-results?limit=500"),
    api("/queue"),
  ]);
  state.stats = stats;
  state.submissions = submissions;
  state.images = images;
  state.results = results;
  state.queue = queue;
  clearDeferredViews();
  populateImageLibraryOptions();
  renderStats();
  renderTable("submissions");
  renderTable("images");
  renderTable("queue");
  stampRefresh();
}

async function refreshForPolling() {
  const [stats, submissions, results, queue] = await Promise.all([
    api("/admin/dashboard/stats"),
    api("/submissions?limit=500"),
    api("/process-results?limit=500"),
    api("/queue"),
  ]);

  const changed = {
    stats: hasDataChanged(state.stats, stats),
    submissions: hasDataChanged(state.submissions, submissions),
    results: hasDataChanged(state.results, results),
    queue: hasDataChanged(state.queue, queue),
  };

  state.stats = stats;
  state.submissions = submissions;
  state.results = results;
  state.queue = queue;

  if (changed.stats) renderStats();
  if (changed.queue) renderOrDeferTable("queue");
  if (changed.submissions || changed.results || changed.queue) renderOrDeferTable("submissions");
  flushDeferredViews();
  stampRefresh();
}

async function refreshImages() {
  state.images = await api("/images");
  populateImageLibraryOptions();
  renderTable("images");
}

function hasDataChanged(current, next) {
  return JSON.stringify(current) !== JSON.stringify(next);
}

function renderOrDeferTable(view) {
  if (isViewRenderProtected(view)) {
    state.deferredViews[view] = true;
    return;
  }
  state.deferredViews[view] = false;
  renderTable(view);
}

function flushDeferredViews() {
  Object.keys(state.deferredViews).forEach((view) => {
    if (!state.deferredViews[view] || isViewRenderProtected(view)) return;
    state.deferredViews[view] = false;
    renderTable(view);
  });
}

function clearDeferredViews() {
  Object.keys(state.deferredViews).forEach((view) => {
    state.deferredViews[view] = false;
  });
}

function isViewRenderProtected(view) {
  if (view !== getActiveView()) return false;

  const panel = document.querySelector(`[data-panel="${view}"]`);
  const active = document.activeElement;
  if (panel && active && panel.contains(active) && isInteractiveElement(active)) return true;

  if (view === "submissions") {
    return state.submissionFormDirty || isResultReviewActive();
  }

  return false;
}

function getActiveView() {
  return document.querySelector(".view.active")?.dataset.panel || "dashboard";
}

function isInteractiveElement(node) {
  return Boolean(node?.closest?.("input, textarea, select, button, [contenteditable='true']"));
}

function isResultReviewActive() {
  const active = document.activeElement;
  const shell = document.querySelector(".result-review-shell");
  return Boolean(shell && active && shell.contains(active));
}

function renderStats() {
  if (!state.stats) return;
  document.getElementById("submission-count").textContent = String(state.stats.submission_count);
  document.getElementById("queue-count").textContent = String(state.stats.queue_count);
  document.getElementById("processing-status").textContent = state.stats.processing_enabled ? "Enabled" : "Paused";
  document.getElementById("worker-status").textContent = formatWorkerStatus(state.stats);
}

function renderTable(view) {
  const config = tableConfigs[view];
  const body = config.body;
  const rows = getVisibleRows(view);
  const visibleRowKeys = new Set(rows.map((item) => getRowKey(view, item)));
  state.selection[view] = state.selection[view].filter((id) => visibleRowKeys.has(id));
  const visibleSelectedIds = new Set(state.selection[view]);
  const pageRows = getPaginatedRows(view, rows);
  body.innerHTML = "";
  if (!pageRows.length) {
    body.innerHTML = `<tr><td colspan="${config.columns.length + 1}" class="text-secondary">No matching rows.</td></tr>`;
  }
  pageRows.forEach((item) => {
    const rowKey = getRowKey(view, item);
    const tr = document.createElement("tr");
    if (visibleSelectedIds.has(rowKey)) tr.classList.add("selected");
    const checkbox = document.createElement("td");
    checkbox.innerHTML = `<input type="checkbox" ${visibleSelectedIds.has(rowKey) ? "checked" : ""} aria-label="Select row" />`;
    checkbox.firstElementChild.addEventListener("change", () => toggleSelection(view, rowKey));
    tr.appendChild(checkbox);
    config.columns.forEach(([key]) => {
      const td = document.createElement("td");
      td.innerHTML = formatTableCell(view, key, item[key]);
      tr.appendChild(td);
    });
    tr.addEventListener("click", (event) => {
      if (event.target.matches("input")) return;
      state.selection[view] = [rowKey];
      if (view === "submissions") state.selectedSubmissionResultId = null;
      renderTable(view);
    });
    body.appendChild(tr);
  });
  renderPagination(view, rows.length);
  renderSortIndicators(view);
  renderDetails(view);
}

function getVisibleRows(view) {
  const rows = [...state[view]];
  const filtered = rows.filter((item) => JSON.stringify(item).toLowerCase().includes(state.filter[view]));
  const { key, direction } = state.sort[view];
  filtered.sort((left, right) => compareValues(left[key], right[key], direction));
  return filtered;
}

function getPaginatedRows(view, rows) {
  const pagination = state.pagination[view];
  const totalPages = getTotalPages(rows.length, pagination.pageSize);
  pagination.page = Math.min(Math.max(pagination.page, 1), totalPages);
  const start = (pagination.page - 1) * pagination.pageSize;
  return rows.slice(start, start + pagination.pageSize);
}

function getTotalPages(rowCount, pageSize) {
  return Math.max(1, Math.ceil(rowCount / pageSize));
}

function renderPagination(view, rowCount) {
  const config = tableConfigs[view];
  const pagination = state.pagination[view];
  const totalPages = getTotalPages(rowCount, pagination.pageSize);
  const start = rowCount ? (pagination.page - 1) * pagination.pageSize + 1 : 0;
  const end = Math.min(rowCount, pagination.page * pagination.pageSize);
  const pageButtons = buildPaginationButtons(view, pagination.page, totalPages);

  config.pagination.innerHTML = `
    <div class="table-page-summary text-secondary">
      Showing ${start}-${end} of ${rowCount}
    </div>
    <label class="page-size-control">
      <span class="text-secondary">Rows</span>
      <select class="form-select form-select-sm" data-view="${view}" data-page-size>
        ${PAGE_SIZE_OPTIONS.map((size) => `<option value="${size}" ${size === pagination.pageSize ? "selected" : ""}>${size}</option>`).join("")}
      </select>
    </label>
    <nav aria-label="${getViewLabel(view)} table pages">
      <ul class="pagination pagination-sm mb-0">
        <li class="page-item ${pagination.page === 1 ? "disabled" : ""}">
          <button class="page-link" type="button" data-view="${view}" data-page="${pagination.page - 1}" ${pagination.page === 1 ? "disabled" : ""}>Previous</button>
        </li>
        ${pageButtons}
        <li class="page-item ${pagination.page === totalPages ? "disabled" : ""}">
          <button class="page-link" type="button" data-view="${view}" data-page="${pagination.page + 1}" ${pagination.page === totalPages ? "disabled" : ""}>Next</button>
        </li>
      </ul>
    </nav>
  `;
}

function buildPaginationButtons(view, currentPage, totalPages) {
  const pages = getPaginationWindow(currentPage, totalPages);
  return pages
    .map((page) => {
      if (page === "ellipsis") {
        return '<li class="page-item disabled"><span class="page-link">…</span></li>';
      }
      const active = page === currentPage;
      return `
        <li class="page-item ${active ? "active" : ""}">
          <button class="page-link" type="button" data-view="${view}" data-page="${page}" ${active ? 'aria-current="page"' : ""}>${page}</button>
        </li>
      `;
    })
    .join("");
}

function getPaginationWindow(currentPage, totalPages) {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, index) => index + 1);
  }
  const pages = new Set([1, totalPages, currentPage, currentPage - 1, currentPage + 1]);
  const sorted = [...pages].filter((page) => page >= 1 && page <= totalPages).sort((left, right) => left - right);
  const windowed = [];
  sorted.forEach((page, index) => {
    if (index > 0 && page - sorted[index - 1] > 1) {
      windowed.push("ellipsis");
    }
    windowed.push(page);
  });
  return windowed;
}

function renderSortIndicators(view) {
  const config = tableConfigs[view];
  const current = state.sort[view];
  config.head.querySelectorAll("[data-sort-column]").forEach((th) => {
    const key = th.dataset.sortColumn;
    const button = th.querySelector(".sort-button");
    const icon = th.querySelector(".sort-icon");
    const srText = th.querySelector(".visually-hidden");
    const active = key === current.key;
    const directionLabel = current.direction === "asc" ? "ascending" : "descending";
    th.setAttribute("aria-sort", active ? directionLabel : "none");
    button.classList.toggle("active", active);
    icon.textContent = active ? (current.direction === "asc" ? "▲" : "▼") : "↕";
    srText.textContent = active ? `Sorted ${directionLabel}` : "Not sorted";
  });
}

function getViewLabel(view) {
  const labels = {
    submissions: "Submissions",
    images: "Images",
    queue: "Queue",
  };
  return labels[view] || humanizeFieldName(view);
}

function toggleSelection(view, id) {
  const next = new Set(state.selection[view]);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  state.selection[view] = [...next];
  if (view === "submissions") state.selectedSubmissionResultId = null;
  renderTable(view);
}

function renderDetails(view) {
  const config = tableConfigs[view];
  const selected = state[view].find((item) => getRowKey(view, item) === state.selection[view][0]);
  const imagePreview = document.getElementById("image-preview");
  const imagePreviewEmpty = document.getElementById("image-preview-empty");
  if (view === "submissions") {
    updateSubmissionDetailActions(selected);
  }
  config.details.innerHTML = "";
  if (!selected) {
    config.details.innerHTML = "<dt>Status</dt><dd>No row selected.</dd>";
    if (view === "submissions") {
      renderSubmissionResults(null);
    }
    if (view === "images") {
      imagePreview.hidden = true;
      imagePreview.removeAttribute("src");
      imagePreviewEmpty.hidden = false;
    }
    return;
  }
  renderObjectDetails(config.details, selected, view);
  if (view === "submissions") {
    renderSubmissionResults(selected);
  }
  if (view === "images") {
    imagePreview.src = selected.previewUrl;
    imagePreview.hidden = false;
    imagePreviewEmpty.hidden = true;
  }
}

function renderSubmissionResults(submission) {
  const body = document.getElementById("submission-result-body");
  const count = document.getElementById("submission-result-count");
  const details = document.getElementById("submission-result-details");
  body.innerHTML = "";
  details.innerHTML = "";
  if (!submission) {
    count.textContent = "";
    renderResultReview(null);
    return;
  }

  const results = getResultsForSubmission(submission.id);
  count.textContent = `${results.length} result${results.length === 1 ? "" : "s"}`;
  if (!results.length) {
    body.innerHTML = '<tr><td colspan="5" class="text-secondary">No results for this submission.</td></tr>';
    renderResultReview(null);
    return;
  }

  if (!results.some((result) => result.id === state.selectedSubmissionResultId)) {
    state.selectedSubmissionResultId = results[0].id;
  }

  results.forEach((result) => {
    const tr = document.createElement("tr");
    tr.className = result.id === state.selectedSubmissionResultId ? "table-primary" : "";
    tr.innerHTML = `
      <td>${escapeHtml(result.id)}</td>
      <td>${formatStatus(result.status)}</td>
      <td>${formatApproved(result.approved)}</td>
      <td>${escapeHtml(formatDateTime(result.created))}</td>
      <td>${escapeHtml(formatDateTime(result.processCompleted))}</td>
    `;
    tr.addEventListener("click", () => {
      state.selectedSubmissionResultId = result.id;
      state.selectedResultField = null;
      renderSubmissionResults(submission);
    });
    body.appendChild(tr);
  });

  const selectedResult = results.find((result) => result.id === state.selectedSubmissionResultId) || results[0];
  renderResultDetails(selectedResult);
  renderResultReview(selectedResult);
}

function getResultsForSubmission(submissionId) {
  return state.results
    .filter((result) => result.submissionId === submissionId)
    .sort((left, right) => compareValues(left.created, right.created, "desc"));
}

function renderObjectDetails(container, item, view) {
  container.innerHTML = "";
  const hiddenKeys = new Set(["processResults", "previewUrl", "matchResults", "combinedImageUrl"]);
  Object.entries(item)
    .filter(([key]) => !hiddenKeys.has(key))
    .forEach(([key, value]) => {
      const dt = document.createElement("dt");
      dt.textContent = getFieldLabel(key);
      const dd = document.createElement("dd");
      dd.innerHTML = formatDetailValue(view, key, value);
      container.appendChild(dt);
      container.appendChild(dd);
    });
}

function renderResultDetails(result) {
  const details = document.getElementById("submission-result-details");
  details.innerHTML = "";
  const items = [
    ["id", result.id],
    ["submissionId", result.submissionId],
    ["status", result.status],
    ["approved", result.approved],
    ["processStarted", result.processStarted],
    ["processCompleted", result.processCompleted],
    ["errorMessage", result.errorMessage],
  ];
  items.forEach(([label, value]) => {
    const dt = document.createElement("dt");
    dt.textContent = getFieldLabel(label);
    const dd = document.createElement("dd");
    dd.innerHTML = formatDetailValue("results", label, value);
    details.appendChild(dt);
    details.appendChild(dd);
  });
  (result.matchResults || []).forEach((match) => {
    const dt = document.createElement("dt");
    dt.textContent = match.label;
    const dd = document.createElement("dd");
    dd.textContent = buildMatchSummary(match);
    details.appendChild(dt);
    details.appendChild(dd);
  });
}

function renderResultReview(result) {
  const empty = document.getElementById("result-image-empty");
  const stage = document.getElementById("result-image-stage");
  const image = document.getElementById("result-image");
  const legend = document.getElementById("result-legend");
  const overlay = document.getElementById("result-image-overlay");

  legend.innerHTML = "";
  overlay.innerHTML = "";
  image.onload = null;
  image.onerror = null;
  empty.textContent = "Select a result to review field matches on the processed image.";

  if (!result) {
    stage.hidden = true;
    empty.hidden = false;
    image.removeAttribute("src");
    return;
  }

  const matches = result.matchResults || [];
  legend.innerHTML = matches.map((match) => buildResultPill(match)).join("");
  const selectedField = getSelectedResultField(matches);
  setActiveResultPill(legend, selectedField);
  legend.querySelectorAll("[data-result-field]").forEach((pill) => {
    pill.addEventListener("click", () => {
      state.selectedResultField = pill.dataset.resultField;
      setActiveResultPill(legend, state.selectedResultField);
      renderResultBoxes(matches, state.selectedResultField);
    });
  });
  empty.hidden = false;
  stage.hidden = true;

  if (!result.combinedImageUrl) {
    return;
  }

  const showLoadedImage = () => {
    renderResultBoxes(matches, getSelectedResultField(matches));
    stage.hidden = false;
    empty.hidden = true;
  };
  image.onload = showLoadedImage;
  image.onerror = () => {
    stage.hidden = true;
    empty.hidden = false;
    empty.textContent = "Processed image could not be loaded.";
  };

  if (image.getAttribute("src") !== result.combinedImageUrl) {
    image.src = result.combinedImageUrl;
  } else if (image.complete && image.naturalWidth) {
    showLoadedImage();
  }
}

function getSelectedResultField(matches) {
  if (matches.some((match) => match.field === state.selectedResultField)) {
    return state.selectedResultField;
  }
  return null;
}

function setActiveResultPill(legend, selectedField) {
  legend.querySelectorAll("[data-result-field]").forEach((pill) => {
    const active = Boolean(selectedField) && pill.dataset.resultField === selectedField;
    pill.classList.toggle("active", active);
    pill.setAttribute("aria-pressed", String(active));
  });
}

function renderResultBoxes(matches, selectedField = null) {
  const image = document.getElementById("result-image");
  const overlay = document.getElementById("result-image-overlay");
  overlay.innerHTML = "";
  if (!image.naturalWidth || !image.naturalHeight) return;

  const scaleX = image.clientWidth / image.naturalWidth;
  const scaleY = image.clientHeight / image.naturalHeight;

  matches
    .filter((match) => Array.isArray(match.bbox) && match.bbox.length)
    .filter((match) => !selectedField || match.field === selectedField)
    .forEach((match) => {
      const rect = bboxToRect(match.bbox);
      if (!rect) return;
      const box = document.createElement("div");
      box.className = `result-box ${getResultStatusClass(match)}${selectedField ? " active" : ""}`;
      box.title = buildMatchSummary(match);
      box.style.left = `${rect.left * scaleX}px`;
      box.style.top = `${rect.top * scaleY}px`;
      box.style.width = `${Math.max(rect.width * scaleX, 2)}px`;
      box.style.height = `${Math.max(rect.height * scaleY, 2)}px`;
      overlay.appendChild(box);
    });
}

function bboxToRect(bbox) {
  const points = bbox.filter((point) => Array.isArray(point) && point.length >= 2);
  if (!points.length) return null;
  const xs = points.map((point) => Number(point[0])).filter(Number.isFinite);
  const ys = points.map((point) => Number(point[1])).filter(Number.isFinite);
  if (!xs.length || !ys.length) return null;
  const left = Math.min(...xs);
  const right = Math.max(...xs);
  const top = Math.min(...ys);
  const bottom = Math.max(...ys);
  return { left, top, width: right - left, height: bottom - top };
}

function buildResultPill(match) {
  const statusClass = getResultStatusClass(match);
  const requirement = match.required ? "Required" : "Optional";
  const status = match.matched ? "matched" : "not matched";
  const icon = match.matched ? "check-circle" : match.required ? "x-circle" : "dash-circle";
  return `<button type="button" class="result-pill ${statusClass}" data-result-field="${escapeHtml(match.field)}" aria-pressed="false" title="${escapeHtml(buildMatchSummary(match))}"><span class="status-icon" aria-hidden="true">${iconText(icon)}</span>${escapeHtml(match.label)}: ${requirement}, ${status}</button>`;
}

function buildMatchSummary(match) {
  const requirement = match.required ? "Required" : "Optional";
  const status = match.matched ? "matched" : "not matched";
  const matchedText = match.matchedText ? ` Found: ${match.matchedText}.` : "";
  const closestText = !match.matched && match.closestText ? ` Closest OCR text: ${match.closestText}.` : "";
  return `${requirement}. ${status}.${matchedText}${closestText} Expected: ${match.expectedText}.`;
}

function getResultStatusClass(match) {
  if (match.matched) return "matched";
  return match.required ? "required-missed" : "optional-missed";
}

function getRowKey(view, item) {
  return view === "images" ? item.path : item.id;
}

function formatTableValue(view, key, value) {
  if (view === "images" && key === "sizeBytes") {
    return formatBytes(value);
  }
  return value;
}

function formatTableCell(view, key, value) {
  if (key === "approved") return formatApproved(value);
  if (key === "status") return formatStatus(value);
  if (dateFields.has(key)) return escapeHtml(formatDateTime(value));
  return escapeHtml(formatCell(formatTableValue(view, key, value)));
}

function formatDetailValue(view, key, value) {
  if (key === "approved") return formatApproved(value);
  if (key === "status") return formatStatus(value);
  if (dateFields.has(key)) return escapeHtml(formatDateTime(value));
  if (view === "images" && key === "sizeBytes") return escapeHtml(formatBytes(value));
  if (typeof value === "object" && value !== null) return escapeHtml(JSON.stringify(value, null, 2));
  return escapeHtml(formatCell(value));
}

function getFieldLabel(key) {
  return fieldLabels[key] || humanizeFieldName(key);
}

function humanizeFieldName(key) {
  return String(key)
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatApproved(value) {
  if (value === null || value === undefined || value === "") {
    return '<span class="badge text-bg-secondary"><span class="status-icon" aria-hidden="true">?</span>Pending</span>';
  }
  if (value) {
    return '<span class="badge text-bg-success"><span class="status-icon" aria-hidden="true">✓</span>Approved</span>';
  }
  return '<span class="badge text-bg-danger"><span class="status-icon" aria-hidden="true">×</span>Not Approved</span>';
}

function formatStatus(value) {
  const status = formatCell(value);
  const normalized = String(value || "").toLowerCase();
  const classes = {
    complete: "text-bg-success",
    queued: "text-bg-secondary",
    processing: "text-bg-primary",
    failed: "text-bg-danger",
    cancelled: "text-bg-warning",
  };
  const icons = {
    complete: "✓",
    queued: "○",
    processing: "↻",
    failed: "×",
    cancelled: "!",
  };
  const badgeClass = classes[normalized] || "text-bg-secondary";
  const icon = icons[normalized] || "○";
  return `<span class="badge ${badgeClass}"><span class="status-icon" aria-hidden="true">${icon}</span>${escapeHtml(status)}</span>`;
}

function iconText(name) {
  const icons = {
    "check-circle": "✓",
    "x-circle": "×",
    "dash-circle": "○",
  };
  return icons[name] || "○";
}

function loadSelectedSubmissionForEdit() {
  const selected = state.submissions.find((item) => item.id === state.selection.submissions[0]);
  if (!selected) return;
  state.editingSubmissionId = selected.id;
  state.submissionFormDirty = false;
  document.getElementById("submission-form-title").textContent = `Edit Submission #${selected.id}`;
  document.getElementById("field-category").value = selected.category || CATEGORY_OPTIONS[0];
  document.getElementById("field-brand").value = selected.brand || "";
  document.getElementById("field-classType").value = selected.classType || "";
  document.getElementById("field-address").value = selected.address || "";
  document.getElementById("field-netContents").value = selected.netContents || "";
  document.getElementById("field-alcohol").value = selected.alcohol || "";
  document.getElementById("field-origin").value = selected.origin || "";
  document.getElementById("field-appellation").value = selected.appellation || "";
  document.getElementById("field-warning").value = GOVERNMENT_WARNING;
  state.submissionImagePath = selected.images || "";
  state.submissionImageLibraryFilter = "";
  document.getElementById("image-library-search").value = "";
  populateImageLibraryOptions();
  syncSubmissionFormVisibility();
  renderSelectedImage();
}

function resetSubmissionForm() {
  state.editingSubmissionId = null;
  state.submissionImagePath = "";
  state.submissionImageLibraryFilter = "";
  state.submissionFormDirty = false;
  document.getElementById("submission-form-title").textContent = "Create Submission";
  document.getElementById("submission-form").reset();
  document.getElementById("field-category").value = CATEGORY_OPTIONS[0];
  document.getElementById("field-warning").value = GOVERNMENT_WARNING;
  document.getElementById("submission-form-error").hidden = true;
  document.getElementById("image-library-search").value = "";
  populateImageLibraryOptions();
  syncSubmissionFormVisibility();
  renderSelectedImage();
}

async function saveSubmission(event) {
  event.preventDefault();
  const error = document.getElementById("submission-form-error");
  error.hidden = true;

  const category = document.getElementById("field-category").value;
  const payload = {
    category,
    brand: document.getElementById("field-brand").value.trim(),
    classType: document.getElementById("field-classType").value.trim(),
    address: document.getElementById("field-address").value.trim(),
    netContents: document.getElementById("field-netContents").value.trim(),
    alcohol: document.getElementById("field-alcohol").value.trim() || null,
    origin: document.getElementById("field-origin").value.trim() || null,
    appellation: category === "Wine" ? document.getElementById("field-appellation").value.trim() || null : null,
    warning: GOVERNMENT_WARNING,
    images: state.submissionImagePath,
  };

  try {
    if (state.editingSubmissionId) {
      await api(`/submissions/${state.editingSubmissionId}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
      showToast({
        title: `Submission #${state.editingSubmissionId} updated`,
        message: "Changes were saved.",
      });
    } else {
      await api("/submissions", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      showToast({
        title: "Submission created",
        message: getQueueSuccessMessage("The submission was saved and queued."),
      });
    }
    resetSubmissionForm();
    await refreshAll();
  } catch (err) {
    error.textContent = err.message;
    error.hidden = false;
    showToast({
      title: "Submission save failed",
      message: err.message,
      tone: "error",
    });
  }
}

async function queueSelectedSubmission() {
  const selected = state.submissions.find((item) => item.id === state.selection.submissions[0]);
  if (!selected) return;

  const queueStatus = getSubmissionQueueStatus(selected.id);
  if (queueStatus) {
    const detail = queueStatus === "processing" ? "This submission is already processing." : "This submission is already queued.";
    setSubmissionDetailMessage(detail);
    showToast({
      title: `Submission #${selected.id} unavailable`,
      message: detail,
      tone: "error",
    });
    return;
  }

  setSubmissionDetailMessage("Adding submission to queue.");
  try {
    await api(`/queue/${selected.id}`, { method: "POST" });
    setSubmissionDetailMessage(`Submission #${selected.id} added to queue.`);
    showToast({
      title: `Submission #${selected.id} queued`,
      message: getQueueSuccessMessage("The submission was added to the processing queue."),
    });
    await refreshAll();
  } catch (err) {
    setSubmissionDetailMessage(err.message, true);
    showToast({
      title: "Queue action failed",
      message: err.message,
      tone: "error",
    });
  }
}

async function deleteSelectedSubmissions() {
  const count = state.selection.submissions.length;
  if (!count) return;
  try {
    await deleteMany(state.selection.submissions, (id) => `/submissions/${id}`);
    state.selection.submissions = [];
    showToast({
      title: count === 1 ? "Submission deleted" : "Submissions deleted",
      message: `${count} submission${count === 1 ? "" : "s"} removed.`,
    });
    await refreshAll();
  } catch (err) {
    showToast({
      title: "Delete failed",
      message: err.message,
      tone: "error",
    });
  }
}

async function deleteSelectedImages() {
  const selectedPaths = state.images
    .filter((item) => state.selection.images.includes(item.path))
    .map((item) => item.path);
  if (!selectedPaths.length) return;
  try {
    await Promise.all(
      selectedPaths.map((path) =>
        api(`/images?path=${encodeURIComponent(path)}`, {
          method: "DELETE",
        }),
      ),
    );
    state.selection.images = [];
    showToast({
      title: selectedPaths.length === 1 ? "Image deleted" : "Images deleted",
      message: `${selectedPaths.length} image${selectedPaths.length === 1 ? "" : "s"} removed.`,
    });
    await refreshAll();
  } catch (err) {
    showToast({
      title: "Image delete failed",
      message: err.message,
      tone: "error",
    });
  }
}

async function deleteSelectedQueueItems() {
  const bySubmission = state.queue
    .filter((item) => state.selection.queue.includes(item.id))
    .map((item) => item.submissionId);
  if (!bySubmission.length) return;
  try {
    await deleteMany(bySubmission, (submissionId) => `/queue/${submissionId}`);
    state.selection.queue = [];
    showToast({
      title: bySubmission.length === 1 ? "Queue item removed" : "Queue items removed",
      message: `${bySubmission.length} queued submission${bySubmission.length === 1 ? "" : "s"} cancelled.`,
    });
    await refreshAll();
  } catch (err) {
    showToast({
      title: "Queue delete failed",
      message: err.message,
      tone: "error",
    });
  }
}

async function clearQueue() {
  try {
    const response = await api("/queue", { method: "DELETE" });
    state.selection.queue = [];
    showToast({
      title: "Queue cleared",
      message: `${response.cancelled} queued item${response.cancelled === 1 ? "" : "s"} cancelled.`,
    });
    await refreshAll();
  } catch (err) {
    showToast({
      title: "Queue clear failed",
      message: err.message,
      tone: "error",
    });
  }
}

async function deleteMany(ids, toPath) {
  if (!ids.length) return;
  await Promise.all(ids.map((id) => api(toPath(id), { method: "DELETE" })));
}

async function updateProcessing(path) {
  try {
    await api(path, { method: "POST" });
    showToast({
      title: path.endsWith("/pause") ? "Processing paused" : "Processing resumed",
    });
    await refreshAll();
  } catch (err) {
    showToast({
      title: "Processing update failed",
      message: err.message,
      tone: "error",
    });
  }
}

function setSelectedImagePath(path) {
  state.submissionImagePath = path;
  renderSelectedImage();
}

function clearSelectedImage() {
  state.submissionImagePath = "";
  renderSelectedImage();
}

function renderSelectedImage() {
  const container = document.getElementById("image-selection");
  container.innerHTML = "";
  if (!state.submissionImagePath) {
    container.innerHTML = '<div class="image-list-empty muted">No image path selected.</div>';
    return;
  }

  const previewUrl = getImagePreviewUrl(state.submissionImagePath);
  const item = document.createElement("div");
  item.className = "image-list-item";
  item.innerHTML = `
    <div class="image-list-main">
      <img class="image-list-thumb" src="${previewUrl}" alt="" loading="lazy" />
      <div class="image-list-meta">
        <span class="image-path">${escapeHtml(state.submissionImagePath)}</span>
      </div>
    </div>
    <button class="ghost" type="button" data-remove-image="true">Clear</button>
  `;
  item.querySelector("img").addEventListener("error", (event) => {
    event.target.replaceWith(buildMissingThumbnail());
  });
  container.appendChild(item);
}

function populateImageLibraryOptions() {
  const container = document.getElementById("image-library-results");
  if (!container) return;
  const query = state.submissionImageLibraryFilter;
  if (!query) {
    renderImageLibraryPrompt();
    return;
  }
  const filteredImages = state.images.filter((image) =>
    `${image.name || ""} ${image.path}`.toLowerCase().includes(query),
  );
  if (!filteredImages.length) {
    container.innerHTML = '<div class="image-library-empty muted">No matching images.</div>';
    return;
  }

  container.innerHTML = filteredImages
    .slice(0, IMAGE_SEARCH_LIMIT)
    .map(
      (image) => `
        <button class="image-library-result" type="button" data-image-path="${escapeHtml(image.path)}">
          <span class="image-library-result-name">${escapeHtml(image.name || image.path)}</span>
          <span class="image-library-result-path">${escapeHtml(image.path)}</span>
        </button>
      `,
    )
    .join("");
}

function renderImageLibraryPrompt() {
  const container = document.getElementById("image-library-results");
  if (!container) return;
  container.innerHTML = '<div class="image-library-empty muted">Start typing to search images.</div>';
}

function syncSubmissionFormVisibility() {
  const category = document.getElementById("field-category").value;
  document.querySelectorAll("[data-show-when-category]").forEach((node) => {
    const visible = node.dataset.showWhenCategory === category;
    node.hidden = !visible;
    if (!visible) {
      const input = node.querySelector("input, textarea, select");
      if (input) input.value = "";
    }
  });
}

function getFieldBadgeText(fieldConfig) {
  return fieldConfig.required ? "Required" : "Optional";
}

async function uploadImage(file) {
  const error = document.getElementById("submission-form-error");
  error.hidden = true;
  try {
    const path = await uploadImageFile(file);
    await refreshImages();
    setSelectedImagePath(path);
    showToast({
      title: "Image uploaded",
      message: "The uploaded image is selected for this submission.",
    });
  } catch (err) {
    error.textContent = err.message;
    error.hidden = false;
    showToast({
      title: "Image upload failed",
      message: err.message,
      tone: "error",
    });
  }
}

async function onImagesLibraryUpload(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  try {
    const uploadedPath = await uploadImageFile(file);
    setSelectedImagePath(uploadedPath);
    showToast({
      title: "Image uploaded",
      message: "The image library has been updated.",
    });
    await refreshImages();
  } catch (err) {
    showToast({
      title: "Image upload failed",
      message: err.message,
      tone: "error",
    });
  } finally {
    event.target.value = "";
  }
}

async function uploadImageFile(file) {
  const formData = new FormData();
  formData.append("image", file);
  const response = await api("/images/upload", {
    method: "POST",
    body: formData,
    isFormData: true,
  });
  return response.path;
}

function compareValues(left, right, direction) {
  const order = direction === "asc" ? 1 : -1;
  const a = left ?? "";
  const b = right ?? "";
  if (typeof a === "number" && typeof b === "number") return (a - b) * order;
  return String(a).localeCompare(String(b)) * order;
}

function formatCell(value) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return String(value);
}

function formatDateTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return formatCell(value);
  const pad = (part) => String(part).padStart(2, "0");
  return [
    pad(date.getMonth() + 1),
    pad(date.getDate()),
    date.getFullYear(),
  ].join("/") + ` ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

function formatBytes(value) {
  const size = Number(value);
  if (!Number.isFinite(size)) return String(value);
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function getImagePreviewUrl(path) {
  return `/images/file?path=${encodeURIComponent(path)}`;
}

function buildMissingThumbnail() {
  const fallback = document.createElement("div");
  fallback.className = "image-list-thumb image-list-thumb-missing";
  fallback.textContent = "No preview";
  return fallback;
}

function updateSubmissionDetailActions(selected) {
  const queueButton = document.getElementById("submission-queue");
  const editButton = document.getElementById("submission-edit");
  const canAct = Boolean(selected);
  queueButton.disabled = !canAct;
  editButton.disabled = !canAct;
  queueButton.textContent = "Add to Queue";
  if (!selected) {
    setSubmissionDetailMessage("");
    return;
  }

  const queueStatus = getSubmissionQueueStatus(selected.id);
  if (queueStatus === "queued") {
    queueButton.disabled = true;
    queueButton.textContent = "Queued";
  } else if (queueStatus === "processing") {
    queueButton.disabled = true;
    queueButton.textContent = "Processing";
  }
}

function setSubmissionDetailMessage(message, isError = false) {
  const node = document.getElementById("submission-detail-message");
  node.textContent = message;
  node.hidden = !message;
  node.classList.toggle("error", isError);
  node.classList.toggle("muted", !isError);
}

function getSubmissionQueueStatus(submissionId) {
  return state.queue.find((item) => item.submissionId === submissionId)?.status || null;
}

function getQueueSuccessMessage(baseMessage) {
  if (!state.stats?.worker_available) {
    return `${baseMessage} The worker is offline; check the Docker web service logs.`;
  }
  return baseMessage;
}

function formatWorkerStatus(stats) {
  if (!stats) return "Offline";
  if (stats.worker_status === "online") {
    return stats.worker_count === 1 ? "Online (1)" : `Online (${stats.worker_count})`;
  }
  if (stats.worker_status === "unreachable") {
    return "Unreachable";
  }
  return "Offline";
}

function showToast({ title, message = "", tone = "success" }) {
  const region = document.getElementById("toast-region");
  if (!region) return;

  const toast = document.createElement("div");
  toast.className = `toast toast-${tone}`;
  toast.role = tone === "error" ? "alert" : "status";
  toast.innerHTML = `
    <div class="toast-title">${escapeHtml(title)}</div>
    ${message ? `<div class="toast-message">${escapeHtml(message)}</div>` : ""}
  `;
  region.appendChild(toast);

  window.setTimeout(() => {
    toast.remove();
  }, TOAST_MS);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function showLogin() {
  document.getElementById("login-screen").hidden = false;
  document.getElementById("dashboard-screen").hidden = true;
}

function showDashboard() {
  document.getElementById("login-screen").hidden = true;
  document.getElementById("dashboard-screen").hidden = false;
}

function stampRefresh() {
  document.getElementById("last-refresh").textContent = `Updated ${new Date().toLocaleTimeString()}`;
}

let pollHandle = null;
let pollingActive = false;
let pollInFlight = false;

function startPolling() {
  stopPolling();
  pollingActive = true;
  schedulePoll();
}

function stopPolling() {
  pollingActive = false;
  if (pollHandle) window.clearTimeout(pollHandle);
  pollHandle = null;
}

function schedulePoll(delay = getPollDelay()) {
  if (!pollingActive) return;
  if (pollHandle) window.clearTimeout(pollHandle);
  pollHandle = window.setTimeout(runPoll, delay);
}

async function runPoll() {
  pollHandle = null;
  if (!pollingActive) return;
  if (pollInFlight) {
    schedulePoll();
    return;
  }

  pollInFlight = true;
  try {
    await refreshForPolling();
  } catch (err) {
    if (err.message === "Authentication required") {
      handleAuthFailure();
    }
  } finally {
    pollInFlight = false;
    schedulePoll();
  }
}

function getPollDelay() {
  return document.hidden ? POLL_HIDDEN_MS : POLL_MS;
}

function onVisibilityChange() {
  if (!pollingActive || document.hidden) return;
  schedulePoll(0);
}

async function api(path, options = {}) {
  const headers = options.isFormData
    ? { ...(options.headers || {}) }
    : {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      };
  const response = await fetch(path, {
    credentials: "same-origin",
    headers,
    ...options,
  });
  if (response.status === 401) {
    handleAuthFailure();
    throw new Error("Authentication required");
  }
  if (!response.ok) {
    const payload = await safeJson(response);
    throw new Error(payload.detail || "Request failed");
  }
  if (response.status === 204) return null;
  return safeJson(response);
}

async function safeJson(response) {
  const text = await response.text();
  return text ? JSON.parse(text) : {};
}

function handleAuthFailure() {
  stopPolling();
  showLogin();
}
