/* KGSaveManager HTML 前端：单页应用，全部数据来自本地 /api/* 接口。 */
(function () {
  "use strict";

  const state = {
    strings: {},
    lang: "zh",
    tabOrder: ["kgsm", "game", "saves", "editor", "download", "settings"],
    slots: [],
    server: {},
    repos: [],
    mirrors: [],
    versionItems: {},
    editorRows: [],
    editorView: "tree",
    editorExpanded: {},
    paths: {},
    config: {},
    selectedSlot: 0,
    editorSlot: null,      // 编辑器选中的槽位（重画下拉时保留，避免跳回第一项）
    eventSeq: 0,
    page: "kgsm",
  };

  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.prototype.slice.call(document.querySelectorAll(sel));

  function t(key, params) {
    let text = state.strings[key] !== undefined ? state.strings[key] : key;
    if (params) {
      Object.keys(params).forEach((k) => {
        text = text.split("{" + k + "}").join(params[k]);
      });
    }
    return text;
  }

  async function call(method, params) {
    let data;
    try {
      const resp = await fetch("/api/call", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ method: method, params: params || {} }),
      });
      data = await resp.json();
    } catch (e) {
      data = { ok: false, error: String(e) };
    }
    if (!data.ok) {
      pushLog("saves", "ERROR " + (data.error || "call failed"));
      return null;
    }
    return data.result;
  }

  // ---------------- 日志与提示 ----------------
  function pushLog(channel, line) {
    const el = document.getElementById("log-" + channel);
    if (!el) { return; }
    const now = new Date().toLocaleTimeString();
    el.textContent += "[" + now + "] " + line + "\n";
    el.scrollTop = el.scrollHeight;
  }

  function toast(level, message, title) {
    const box = document.createElement("div");
    box.className = "toast " + (level || "info");
    if (title) {
      const head = document.createElement("div");
      head.className = "toast-title";
      head.textContent = title;
      box.appendChild(head);
    }
    const body = document.createElement("div");
    body.textContent = message;
    box.appendChild(body);
    $("#toasts").appendChild(box);
    setTimeout(() => box.remove(), level === "error" ? 9000 : 5000);
  }

  // ---------------- 模态对话框 ----------------
  let modalResolve = null;

  function closeModal(result) {
    $("#modal").hidden = true;
    $("#modal-ok").onclick = null;
    $("#modal-cancel").onclick = null;
    if (modalResolve) {
      const fn = modalResolve;
      modalResolve = null;
      fn(result || { ok: false, text: "" });
    }
  }

  function askDialog(kind, message, title, initial) {
    return new Promise((resolve) => {
      modalResolve = resolve;
      $("#modal-title").textContent = title || "";
      $("#modal-message").textContent = message || "";
      const input = $("#modal-input");
      const area = $("#modal-text");
      const file = $("#modal-file");
      const copy = $("#modal-copy");
      input.hidden = kind !== "text";
      area.hidden = kind !== "manual";
      file.hidden = kind !== "manual";
      copy.hidden = kind !== "manual";
      if (kind === "text") { input.value = initial || ""; input.focus(); }
      if (kind === "manual") {
        area.value = "";
        file.value = "";               // 每次打开都清空上次选的文件
        area.focus();
      }
      copy.onclick = () => { copyLibraryPath(); };
      $("#modal").hidden = false;
      $("#modal-ok").onclick = () => closeModal({
        ok: true,
        text: kind === "manual" ? area.value : input.value,
        file: kind === "manual" ? (file.files[0] || null) : null,
      });
      $("#modal-cancel").onclick = () => closeModal({ ok: false, text: "" });
    });
  }

  function libraryPath() {
    return (state.paths && state.paths.saves) || "";
  }

  async function copyLibraryPath() {
    const path = libraryPath();
    try {
      await navigator.clipboard.writeText(path);
      toast("info", t("msg.path_copied", { path: path }));
    } catch (e) {
      toast("warn", t("msg.clipboard_fail", { e: String(e) }));
    }
  }

  // 应用窗口按横向尺寸调整自己。
  // 背景：Edge/Chrome 的应用窗口尺寸由浏览器配置记住，命令行 --window-size
  // 只在"干净配置"时生效，所以默认配置里窗口常常是方的甚至竖的。
  // 页面自己 resizeTo/moveTo 在应用窗口里是生效的（实测 700x500 / moveTo 均生效），
  // 普通标签页里浏览器会忽略这两个调用，因此可以无条件尝试。
  function fitAppWindow() {
    const params = new URLSearchParams(window.location.search);
    if (params.get("fit") !== "1") { return; }
    if (window.sessionStorage.getItem("kgsm-fit") === "1") { return; }
    const availW = window.screen.availWidth || 1280;
    const availH = window.screen.availHeight || 800;
    let w = Math.min(1320, Math.round(availW * 0.76));
    let h = Math.min(840, Math.round(availH * 0.78));
    if (w / h < 1.5) { w = Math.round(h * 1.55); }   // 保证是横向窗口
    if (w > availW) { w = availW; }
    if (h > availH) { h = availH; }
    // 已经是够宽的横向窗口就不动（尊重用户自己调过的大小）
    const square = window.outerWidth <= window.outerHeight * 1.15;
    const tooSmall = window.outerWidth < w - 80 || window.outerHeight < h - 80;
    if (!square && !tooSmall) { return; }
    try {
      window.moveTo(Math.max(0, Math.round((availW - w) / 2)),
                    Math.max(0, Math.round((availH - h) / 2)));
      window.resizeTo(w, h);
      window.sessionStorage.setItem("kgsm-fit", "1");
    } catch (e) { /* 普通标签页里会被忽略 */ }
  }

  async function answerDialog(id, ok, text) {
    try {
      await fetch("/api/answer", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: id, ok: ok, text: text }),
      });
    } catch (e) { /* 服务可能已退出 */ }
  }

  // ---------------- 渲染 ----------------
  function renderStaticStrings() {
    $$("[data-i18n]").forEach((el) => {
      el.textContent = t(el.getAttribute("data-i18n"));
    });
    document.title = (state.appName || "KGSaveManager") +
      (state.version ? " " + state.version : "");
    const badge = $("#version");
    if (badge) { badge.textContent = state.version || ""; }
  }

  function renderNav() {
    const nav = $("#nav");
    nav.innerHTML = "";
    state.tabOrder.forEach((key, i) => {
      const btn = document.createElement("button");
      const no = document.createElement("span");
      no.className = "side-no";
      no.textContent = String(i + 1).padStart(2, "0");
      const label = document.createElement("span");
      label.textContent = t("tab." + key);
      btn.appendChild(no);
      btn.appendChild(label);
      btn.dataset.page = key;
      btn.onclick = () => showPage(key);
      nav.appendChild(btn);
    });
  }

  function showPage(key) {
    if (state.tabOrder.indexOf(key) < 0) { key = "kgsm"; }
    state.page = key;
    $$(".page").forEach((p) => p.classList.toggle("active", p.id === "page-" + key));
    $$("#nav button").forEach((b) => b.classList.toggle("active", b.dataset.page === key));
    if (key === "editor") { loadEditorTree(); }
    // 记到地址栏：刷新/深链（?page=saves）都回到同一页
    try {
      const url = new URL(window.location.href);
      url.searchParams.set("page", key);
      window.history.replaceState(null, "", url);
    } catch (e) { /* file:// 等环境忽略 */ }
  }

  function renderSlots() {
    const body = $("#slot-rows");
    body.innerHTML = "";
    state.slots.forEach((slot) => {
      const tr = document.createElement("tr");
      if (!slot.exists) { tr.className = "empty"; }

      const radioTd = document.createElement("td");
      const radio = document.createElement("input");
      radio.type = "radio";
      radio.name = "slot";
      radio.checked = slot.index === state.selectedSlot;
      radio.onchange = () => { state.selectedSlot = slot.index; };
      radioTd.appendChild(radio);
      tr.appendChild(radioTd);

      const nameTd = document.createElement("td");
      nameTd.textContent = slot.label;      // 与下拉框同一格式，不再附加文件名
      tr.appendChild(nameTd);

      const timeTd = document.createElement("td");
      timeTd.textContent = slot.time || "";
      tr.appendChild(timeTd);

      const noteTd = document.createElement("td");
      const note = document.createElement("input");
      note.type = "text";
      note.value = slot.note || "";
      note.onchange = async () => {
        await call("save_note", { index: slot.index, text: note.value });
      };
      noteTd.appendChild(note);
      tr.appendChild(noteTd);

      body.appendChild(tr);
    });
  }

  function renderEditorChoices() {
    const sel = $("#ed-slot");
    // 重画下拉时保留用户当前的选择（否则每次点「打开」都会跳回第一项）
    const keep = state.editorSlot !== null && state.editorSlot !== undefined
      ? String(state.editorSlot) : sel.value;
    sel.innerHTML = "";
    (state.editorChoices || []).forEach((item) => {
      const opt = document.createElement("option");
      opt.value = item.index;
      opt.textContent = item.label;
      sel.appendChild(opt);
    });
    if (keep !== "" && keep !== undefined && keep !== null) {
      const hit = Array.from(sel.options).some((o) => o.value === String(keep));
      if (hit) { sel.value = String(keep); }
    }
    if (sel.value === "" && sel.options.length) {
      sel.value = sel.options[0].value;
      state.editorSlot = parseInt(sel.value, 10);
    }
  }

  // 实时模式没有"存档位"概念：把下拉禁用并给出去重提示
  function syncEditorMode() {
    const live = $("#ed-mode").value === "live";
    const sel = $("#ed-slot");
    sel.disabled = live;
    sel.title = live ? t("ed.slot_live_tip") : "";
    if (!live) {
      state.editorSlot = parseInt(sel.value || "0", 10);
    }
  }

  function leafNode(row) {
    const li = document.createElement("li");
    const key = document.createElement("span");
    key.className = "key";
    key.textContent = row.label === "" ? "/" : row.label;
    li.appendChild(key);
    const val = document.createElement("span");
    val.className = "val";
    val.textContent = ": " + (row.value === null ? "null" : row.value);
    val.onclick = async () => {
      const raw = await askDialog("text", t("ed.value_prompt"),
                                  t("ed.value_title"), row.value);
      if (!raw.ok) { return; }
      const res = await call("editor_set_value", { path: row.path, raw: raw.text });
      if (res && res.ok) {
        state.editorRows = res.rows;
        loadEditorTree();
      }
    };
    li.appendChild(val);
    return li;
  }

  // 展开状态按节点路径记录；默认只展开"根那一层"，其余全部收起（对齐原 Tk 版的树）。
  // 记录"展开"而不是"收起"，这样新出现的节点默认是收起的。
  // 根那一层有两个节点：逻辑层的 (root) 行（path 为 null）与存档对象本身（path 为 []），
  // 两个都展开才能立刻看到存档的顶层字段。
  function isRootLevelPath(nodePath) {
    return !nodePath || (Array.isArray(nodePath) && nodePath.length === 0);
  }

  function isNodeExpanded(nodePath, isRoot) {
    const key = JSON.stringify(nodePath);
    if (Object.prototype.hasOwnProperty.call(state.editorExpanded, key)) {
      return !!state.editorExpanded[key];
    }
    return isRoot || isRootLevelPath(nodePath);
  }

  function renderEditorTree() {
    const wrap = $("#ed-tree-wrap");
    wrap.innerHTML = "";
    const rows = state.editorRows || [];
    if (!rows.length) {
      const p = document.createElement("p");
      p.className = "hint";
      p.textContent = t("ed.no_slot");
      wrap.appendChild(p);
      return;
    }
    const built = {};
    rows.forEach((row) => {
      const li = row.kind === "leaf" ? leafNode(row) : document.createElement("li");
      if (row.kind !== "leaf") {
        // 可折叠节点：三角标 + 键名，点三角或键名都能收起/展开
        // 注意根节点的 path 是 null，键统一按 (path || []) 归一化，否则点了没用
        const nodePath = row.path || [];
        const key = JSON.stringify(nodePath);
        const expanded = isNodeExpanded(nodePath, row.parent === null);
        li.className = "branch" + (expanded ? "" : " collapsed");
        const toggle = document.createElement("span");
        toggle.className = "toggle";
        toggle.textContent = expanded ? "▾" : "▸";
        const keyEl = document.createElement("span");
        keyEl.className = "key";
        keyEl.textContent = row.label === "" ? "/" : row.label;
        const hint = document.createElement("span");
        hint.className = "kind";
        hint.textContent = row.kind === "object" ? "{…}" : "[…]";
        const onToggle = (ev) => {
          ev.preventDefault();
          ev.stopPropagation();
          state.editorExpanded[key] = !expanded;
          renderEditorTree();
        };
        toggle.onclick = onToggle;
        keyEl.onclick = onToggle;
        li.appendChild(toggle);
        li.appendChild(keyEl);
        li.appendChild(hint);
        const list = document.createElement("ul");
        li.appendChild(list);
        li._list = list;
      }
      built[row.id] = li;
    });
    const root = document.createElement("ul");
    root.className = "tree";
    rows.forEach((row) => {
      const li = built[row.id];
      if (row.parent === null) { root.appendChild(li); return; }
      const parent = built[row.parent];
      if (parent && parent._list) { parent._list.appendChild(li); }
    });
    wrap.appendChild(root);
  }

  async function loadEditorTree() {
    const res = await call("editor_tree");
    if (res) { state.editorRows = res.rows; }
    renderEditorTree();
  }

  async function loadEditorData() {
    await loadEditorTree();
    const src = await call("editor_source");
    if (src) { $("#ed-source").value = src.text; }
  }

  function renderDownloadOptions() {
    const repo = $("#dl-repo");
    const keep = repo.value;
    repo.innerHTML = "";
    state.repos.forEach((r) => {
      const opt = document.createElement("option");
      opt.value = r.key;
      opt.textContent = r.label;
      repo.appendChild(opt);
    });
    if (keep) { repo.value = keep; }
    const mirror = $("#dl-mirror");
    mirror.innerHTML = "";
    state.mirrors.forEach((m) => {
      const opt = document.createElement("option");
      opt.value = m;
      opt.textContent = m || "github.com";
      mirror.appendChild(opt);
    });
    if (!$("#dl-dir").value && state.defaultTarget) {
      $("#dl-dir").value = state.defaultTarget;
    }
  }

  function renderDownloadVersions() {
    const sel = $("#dl-version");
    const repo = $("#dl-repo").value || "author";
    const items = state.versionItems[repo] || [];
    sel.innerHTML = "";
    items.forEach((item) => {
      const opt = document.createElement("option");
      opt.value = item[2];
      opt.textContent = item[0] === "branch" ? item[1] : item[1] + " (tag)";
      sel.appendChild(opt);
    });
  }

  function renderServerStatus() {
    const s = state.server || {};
    $("#server-status").textContent = s.running
      ? t("msg.server_started", { url: s.url }) + "\n" + t("msg.server_local")
      : t("la.ready");
  }

  function renderSettings() {
    const cfg = state.config || {};
    $("#set-game-dir").value = cfg.game_dir || "";
    $("#set-port").value = cfg.port || "";
    $("#set-browser").value = cfg.browser || "";
    $("#game-dir").value = cfg.game_dir || "";
    $("#game-port").value = cfg.port || "";

    const lang = $("#set-language");
    lang.innerHTML = "";
    [["zh", t("st.lang_zh")], ["en", t("st.lang_en")]].forEach((pair) => {
      const opt = document.createElement("option");
      opt.value = pair[0];
      opt.textContent = pair[1];
      if (pair[0] === state.lang) { opt.selected = true; }
      lang.appendChild(opt);
    });

    $("#set-hint").textContent = t("st.hint", { path: (state.paths || {}).config || "" });
    const p = state.paths || {};
    $("#about-paths").textContent = "data: " + (p.data || "") + "\nlogs: " +
      (p.logs || "") + "\nsaves: " + (p.saves || "");
  }

  function renderAll() {
    renderStaticStrings();
    renderNav();
    renderSlots();
    renderEditorChoices();
    renderDownloadOptions();
    renderDownloadVersions();
    renderServerStatus();
    renderSettings();
    $("#ed-source").hidden = state.editorView !== "source";
    $("#ed-tree-wrap").hidden = state.editorView === "source";
    // 视图/源码开关的选中态
    $$('#page-editor [data-action^="editor-view-"]').forEach((btn) => {
      const isTree = btn.dataset.action === "editor-view-tree";
      btn.classList.toggle("active",
                           isTree === (state.editorView === "tree"));
    });
  }

  function applyState(data) {
    state.strings = data.strings || {};
    state.lang = data.language || "zh";
    state.appName = data.name || "KGSaveManager";
    state.version = data.version || "";
    state.slots = data.slots || [];
    state.server = data.server || {};
    state.repos = data.repos || [];
    state.mirrors = data.mirrors || [];
    state.defaultTarget = data.default_target || "";
    state.paths = data.paths || {};
    state.config = data.config || {};
    state.editorChoices = (data.editor && data.editor.choices) || [];
    renderAll();
  }

  async function refresh() {
    const data = await call("refresh");
    if (data) { applyState(data); }
  }

  // ---------------- 事件轮询 ----------------
  async function pollEvents() {
    try {
      const resp = await fetch("/api/events?since=" + state.eventSeq);
      const data = await resp.json();
      if (data.ok) {
        state.eventSeq = data.next;
        for (const ev of data.events) { await handleEvent(ev); }
      }
    } catch (e) { /* 服务可能正在关闭 */ }
    setTimeout(pollEvents, 700);
  }

  async function handleEvent(ev) {
    switch (ev.type) {
      case "log":
        pushLog(ev.channel, (ev.tag ? ev.tag + " " : "") + ev.message);
        break;
      case "toast":
        toast(ev.level, ev.message, ev.title);
        break;
      case "slots_changed":
        await refresh();
        break;
      case "clipboard":
        try {
          await navigator.clipboard.writeText(ev.text);
          toast("info", t("msg.path_copied", { path: ev.text }));
        } catch (e) {
          toast("warn", t("msg.clipboard_fail", { e: String(e) }));
        }
        break;
      case "dialog":
        askDialog(ev.dialog, ev.message, ev.title, ev.initial).then((r) => {
          answerDialog(ev.id, r.ok, r.text);
        });
        break;
      case "download":
        if (ev.progress !== undefined) { $("#dl-progress").value = ev.progress; }
        break;
      case "download_versions":
        state.versionItems[ev.repo] = ev.items;
        renderDownloadVersions();
        break;
      case "download_done":
        $("#dl-progress").value = 100;
        pushLog("download", t("dl.done", { dir: ev.target }));
        if (ev.set_service) { pushLog("download", t("dl.service_set")); }
        await refresh();
        break;
      case "download_fail":
        pushLog("download", ev.message);
        if (!ev.silent) { toast("error", ev.message); }
        break;
      case "download_canceled":
        pushLog("download", t("dl.cancel"));
        break;
      case "download_test_start":
        $("#dl-test-result").textContent = t("dl.testing");
        break;
      case "download_test_result":
        $("#dl-test-result").textContent = (ev.lines || []).join("\n");
        break;
      case "editor_live":
        // 实时取档完成：core 已更新状态，这里刷新编辑器视图
        if (ev.ok) {
          await refresh();
          await loadEditorData();
        }
        break;
      case "editor_sent":
        // 实时下发的确认结果（提示与日志由 core 推送，这里只刷新视图）
        if (ev.result === true) {
          await refresh();
          await loadEditorData();
        }
        break;
      default:
        break;
    }
  }

  // ---------------- 动作 ----------------
  let settingsTimer = null;

  function collectSettings() {
    return {
      game_dir: $("#set-game-dir").value.trim(),
      port: $("#set-port").value.trim(),
      browser: $("#set-browser").value.trim(),
    };
  }

  // 配置页是"改完即存"：输入框失焦/回车/下拉改变后合并成一次写入
  function saveSettingsSoon() {
    if (settingsTimer) { clearTimeout(settingsTimer); }
    settingsTimer = setTimeout(async () => {
      settingsTimer = null;
      await call("set_config", collectSettings());
      pushLog("saves", t("st.saved"));
    }, 350);
  }

  function bindSettingsAutoSave() {
    ["#set-game-dir", "#set-port", "#set-browser"]
      .forEach((sel) => {
        const el = $(sel);
        el.addEventListener("change", saveSettingsSoon);
        el.addEventListener("blur", saveSettingsSoon);
      });
  }

  // 数据源切换（存档位文件 / 运行中的游戏）→ 同步存档位下拉的可用状态
  function bindEditorMode() {
    $("#ed-mode").addEventListener("change", syncEditorMode);
  }

  const actions = {
    goto: (btn) => showPage(btn.dataset.page),
    doc: async (btn) => {
      await call("open_doc", { name: (btn && btn.dataset.doc) || "guide" });
    },
    extlink: async (btn) => { await call("open_url", { url: btn.dataset.url }); },
    "pick-dir": async (btn) => {
      const target = document.getElementById(btn.dataset.target);
      const res = await askDialog("text", t("dl.dir"), t("ui.browse"), target.value);
      if (res.ok && res.text.trim()) {
        target.value = res.text.trim();
        if (btn.dataset.target.startsWith("set-")) { saveSettingsSoon(); }
      }
    },
    "pick-file": async (btn) => {
      const target = document.getElementById(btn.dataset.target);
      const res = await askDialog("text", t("st.browser"), t("ui.browse"), target.value);
      if (res.ok && res.text.trim()) {
        target.value = res.text.trim();
        if (btn.dataset.target.startsWith("set-")) { saveSettingsSoon(); }
      }
    },
    "browser-default": () => {
      $("#set-browser").value = "";
      saveSettingsSoon();
    },
    "start-server": async () => {
      await call("set_config", {
        game_dir: $("#game-dir").value.trim(),
        port: $("#game-port").value.trim(),
      });
      const res = await call("start_server", { open_browser: true });
      if (res) { state.server = res.server; renderServerStatus(); }
      await refresh();
    },
    "stop-server": async () => {
      const res = await call("stop_server");
      if (res) { state.server = res; renderServerStatus(); }
      pushLog("game", t("msg.server_stopped"));
    },
    "auto-save": async () => { await call("auto_save", { slot: state.selectedSlot }); },
    "auto-load": async () => { await call("auto_load", { slot: state.selectedSlot }); },
    "copy-save": async () => { await call("copy_save", { slot: state.selectedSlot }); },
    "check-library": async () => { await call("check_library"); },
    refresh: async () => { await refresh(); pushLog("saves", t("msg.refreshed")); },
    "rename-slot": async () => {
      const slot = state.slots.find((s) => s.index === state.selectedSlot);
      if (!slot || !slot.exists) { toast("warn", t("err.rename_need_file")); return; }
      const res = await askDialog("text", t("dlg.rename_prompt"),
                                  t("dlg.rename_title"), slot.name);
      if (!res.ok || !res.text.trim()) { return; }
      const out = await call("rename_slot", {
        slot: state.selectedSlot, name: res.text.trim(),
      });
      if (out && out.ok) {
        pushLog("saves", t("msg.file_renamed", { old: slot.name, new: out.name }));
      }
      await refresh();
    },
    "manual-save": async () => {
      const library = libraryPath();
      const message = t("msg.manual_hint") + "\n\n" +
        t("msg.manual_library_hint", { path: library });
      const answer = await askDialog("manual", message,
                                     t("msg.manual_title"), library);
      if (!answer.ok) { return; }
      let text = answer.text || "";
      if (answer.file) {
        try {
          text = await answer.file.text();
        } catch (e) {
          toast("error", String(e));
          return;
        }
      }
      if (!text.trim()) { return; }
      // 成功提示与日志由后端推送；写入后 core 会发 slots_changed 刷新列表
      await call("manual_import_text", {
        slot: state.selectedSlot, text: text,
      });
    },
    "editor-open": async () => {
      const mode = $("#ed-mode").value;
      // 打开新的存档：折叠状态清零（默认只展开根节点）
      state.editorExpanded = {};
      if (mode === "file") {
        const want = parseInt($("#ed-slot").value || "0", 10);
        state.editorSlot = want;
        const res = await call("editor_open_file", { slot: want });
        if (res && res.ok) {
          state.editorChoices = res.state.choices;
          renderEditorChoices();     // 保留刚才选中的槽位，不跳回第一项
          await loadEditorData();
        }
        return;
      }
      const live = await call("editor_open_live");
      if (live && live.pending) {
        // 取档在后台进行，完成后由 editor_live 事件刷新
        pushLog("editor", t("ed.pulling"));
      }
    },
    "editor-write": async () => {
      const sourceText = state.editorView === "source" ? $("#ed-source").value : null;
      const res = await call("editor_write", { source_text: sourceText });
      if (res && res.ok && !res.pending) {
        await loadEditorData();
      }
    },
    "editor-view-tree": () => { state.editorView = "tree"; renderAll(); },
    "editor-view-source": async () => {
      const src = await call("editor_source");
      if (src) { $("#ed-source").value = src.text; }
      state.editorView = "source";
      renderAll();
    },
    "dl-versions": async () => {
      // 按钮显式刷新：忽略后端缓存，强制重新抓取
      await call("download_versions", { repo: $("#dl-repo").value,
                                        refresh: true });
    },
    "dl-test": async () => {
      await call("download_test", {
        repo: $("#dl-repo").value, ref: $("#dl-version").value,
      });
    },
    "dl-start": async () => {
      await call("download_start", {
        repo: $("#dl-repo").value,
        mirror: $("#dl-mirror").value,
        ref: $("#dl-version").value,
        target: $("#dl-dir").value.trim(),
        set_dir: $("#dl-set-dir").checked,
        keep_temp: $("#dl-keep-temp").checked,
      });
    },
    "dl-cancel": async () => { await call("download_cancel"); },
  };

  document.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-action]");
    if (!btn) { return; }
    const fn = actions[btn.dataset.action];
    if (fn) { e.preventDefault(); await fn(btn); }
  });

  // 退出：后端一收到请求就会关服务，页面这次请求拿不到响应是正常的，
  // 所以不能走 call()（它会把连接中断记成 ERROR），也不能等回包。
  async function exitApp() {
    const res = await askDialog("confirm", t("msg.exit_ask"),
                                state.appName || "KGSaveManager", "");
    if (!res.ok) { return; }
    try {
      await fetch("/api/call", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ method: "shutdown", params: {} }),
      });
    } catch (e) { /* 后端已关闭，连接被断开属正常 */ }
    document.body.classList.add("exited");
    const tip = document.getElementById("exit-text");
    if (tip) { tip.textContent = t("msg.exited"); }
    // 应用窗口里 window.close() 是允许的（实测生效）；普通标签页会被忽略，
    // 这时页面顶层的提示会告诉用户可以手动关闭
    try { window.close(); } catch (e) { /* ignore */ }
  }

  $("#btn-exit").onclick = exitApp;
  $("#dl-repo").addEventListener("change", () => actions["dl-versions"]());
  $("#set-language").addEventListener("change", async (e) => {
    const data = await call("set_language", { code: e.target.value });
    if (data) { applyState(data); showPage("settings"); }
  });

  (async function boot() {
    fitAppWindow();
    bindSettingsAutoSave();
    bindEditorMode();
    let init = null;
    try {
      init = await fetch("/api/state").then((r) => r.json());
    } catch (e) { /* 首次加载失败时下面的轮询会重试 */ }
    if (init && init.ok) { applyState(init.result); }
    const want = new URLSearchParams(window.location.search).get("page");
    showPage(want || "kgsm");
    syncEditorMode();
    await call("download_versions", { repo: "author" });
    pollEvents();
  })();
})();
