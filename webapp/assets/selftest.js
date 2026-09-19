/* HTML 前端的自检脚本：仅在地址带 ?selftest=1 时运行。
 *
 * 它通过真实界面路径（点按钮、读 DOM、调 API）跑一遍关键功能，把结果写进
 * #selftest 元素，供自动化验证用（例如 Edge --headless --dump-dom）。
 *
 * 只做只读或可回滚的操作：备注会改回原值，不写任何存档文件。
 */
(function () {
  "use strict";

  if (location.search.indexOf("selftest=1") < 0) { return; }

  const results = [];
  const box = document.createElement("pre");
  box.id = "selftest";
  document.body.appendChild(box);

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  function check(name, ok, fatal) {
    results.push({ name: name, ok: !!ok, fatal: fatal !== false });
    box.textContent = results.map((r) =>
      (r.ok ? "PASS " : (r.fatal ? "FAIL " : "SKIP ")) + r.name).join("\n");
  }

  async function api(method, params) {
    const resp = await fetch("/api/call", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ method: method, params: params || {} }),
    });
    const data = await resp.json();
    return data.ok ? data.result : null;
  }

  async function waitFor(fn, timeout) {
    const deadline = Date.now() + (timeout || 8000);
    while (Date.now() < deadline) {
      if (fn()) { return true; }
      await sleep(120);
    }
    return fn();
  }

  async function run() {
    const nav = document.querySelectorAll("#nav button");
    check("导航渲染出 6 个页面按钮", nav.length === 6);

    const rows = document.querySelectorAll("#slot-rows tr");
    check("存档位渲染出 10 行", rows.length === 10);

    // 切页：每个页面都能激活
    let pageOk = true;
    for (const btn of nav) {
      btn.click();
      await sleep(60);
      const page = document.getElementById("page-" + btn.dataset.page);
      if (!page || !page.classList.contains("active")) { pageOk = false; }
    }
    check("六个页面都能切换", pageOk);

    // 窗口标题与版本徽标
    check("窗口标题含程序名与版本",
          /KGSaveManager|Save Manager/.test(document.title) &&
          /v\d/.test(document.title));
    check("侧栏显示版本号",
          (document.getElementById("version").textContent || "")
            .indexOf("v") === 0);
    const langSel = document.getElementById("set-language");
    check("配置页语言下拉有 2 项", langSel && langSel.options.length === 2);

    // 备注往返（改完再改回去）
    const noteInput = document.querySelector(
      "#slot-rows tr:nth-child(3) input[type=text]");
    if (noteInput) {
      const original = noteInput.value;
      noteInput.value = "selftest-note";
      noteInput.dispatchEvent(new Event("change"));
      await sleep(600);
      const st = await api("refresh");
      check("备注能保存到配置",
            st && st.slots[2] && st.slots[2].note === "selftest-note");
      noteInput.value = original;
      noteInput.dispatchEvent(new Event("change"));
      await sleep(400);
    } else {
      check("备注输入框存在", false);
    }

    // 下载页选项来自 core
    check("仓库下拉 2 项",
          document.querySelectorAll("#dl-repo option").length === 2);
    check("镜像下拉至少 4 项",
          document.querySelectorAll("#dl-mirror option").length >= 4);
    check("版本列表非空（需要网络）",
          document.querySelectorAll("#dl-version option").length >= 1, false);

    // 编辑器：树能渲染出节点（不写回）
    const state = await api("refresh");
    const existing = (state.slots || []).filter((s) => s.exists);
    if (existing.length) {
      const slot = existing[0].index;
      const opened = await api("editor_open_file", { slot: slot });
      const tree = await api("editor_tree");
      check("修改存档页能打开槽位并生成树",
            opened && opened.ok && tree && tree.rows.length > 1);
      const src = await api("editor_source");
      check("源码模式有文本", src && src.text.length > 2);
    } else {
      check("存在可打开的存档位（跳过编辑器检查）", true, false);
    }

    // 事件通道可用
    const events = await fetch("/api/events?since=0").then((r) => r.json());
    check("事件接口可用", events && events.ok === true);

    // 手动导入对话框：浏览选择文件 + 存档库路径说明（只开不写）
    const manualBtn = document.querySelector('[data-action="manual-save"]');
    if (manualBtn) {
      manualBtn.click();
      await sleep(300);
      const modal = document.getElementById("modal");
      const fileInput = document.getElementById("modal-file");
      const message = document.getElementById("modal-message");
      const copyBtn = document.getElementById("modal-copy");
      const library = (state.paths && state.paths.saves) || "";
      check("手动导入弹出对话框", modal && !modal.hidden);
      check("对话框提供文件选择器", fileInput && !fileInput.hidden);
      check("对话框提供复制存档库路径按钮", copyBtn && !copyBtn.hidden);
      check("对话框说明含存档库路径与刷新提示",
            !!library && !!message &&
            message.textContent.indexOf(library) >= 0);
      document.getElementById("modal-cancel").click();
      await sleep(150);
      check("取消后对话框关闭", document.getElementById("modal").hidden);
    } else {
      check("存在手动导入按钮", false);
    }

    const failures = results.filter((r) => !r.ok && r.fatal).length;
    box.textContent += "\nSELFTEST " + (failures ? "FAILED " + failures
                                                 : "OK");
  }

  waitFor(() => document.querySelectorAll("#slot-rows tr").length === 10, 8000)
    .then(run)
    .catch((e) => {
      box.textContent += "\nSELFTEST ERROR " + String(e);
    });
})();
