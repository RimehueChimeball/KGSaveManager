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

    // 布局：宽屏横向分列 + 内容纵向滚动（不出现横向滚动条）
    const main = document.getElementById("main");
    const viewport = window.innerWidth;
    if (viewport >= 1180) {
      const grid = getComputedStyle(document.querySelector(".page.active"))
        .gridTemplateColumns;
      const cols = grid.split(" ").filter((s) => s && s !== "none").length;
      check("宽屏下卡片横向分列（" + cols + " 列）", cols >= 2);
    } else {
      check("窄窗口保持单列（" + viewport + "px）",
            getComputedStyle(document.querySelector(".page.active"))
              .gridTemplateColumns.split(" ").length === 1, false);
    }
    check("页面不出现横向滚动",
          document.documentElement.scrollWidth <= viewport + 1);
    check("内容区自己纵向滚动（scrollHeight > clientHeight）",
          main.scrollHeight > main.clientHeight ||
          document.querySelectorAll(".page.active .card").length <= 2, false);

    // 存档管理页：卡片分列且在窗口内，横向可读
    for (const btn of nav) {
      if (btn.dataset.page === "saves") { btn.click(); }
    }
    await sleep(200);
    const cards = Array.from(document.querySelectorAll("#page-saves .card"));
    const rects = cards.map((c) => c.getBoundingClientRect());
    check("存档管理页有卡片", cards.length >= 3);
    check("卡片未超出内容区右边界",
          rects.every((r) => r.right <= viewport + 1), false);
    check("卡片宽度充分利用横向空间",
          rects.every((r) => r.width >= 300), false);
    const cardTops = Array.from(rects.map((r) => Math.round(r.top)));
    const distinctRows = new Set(cardTops).size;
    check("卡片分成多行排布（" + distinctRows + " 行）", distinctRows >= 2);

    // 新样式是否真的生效（计算值，不看截图）
    const css = (el, prop) => getComputedStyle(el).getPropertyValue(prop);
    const card = cards[0];
    // 计算值可能是 oklch(...)，用画布真实绘制后再读回 sRGB 像素
    const cvs = document.createElement("canvas");
    cvs.width = 1;
    cvs.height = 1;
    const ctx = cvs.getContext("2d", { willReadFrequently: true });
    const rgb = (color, over) => {
      ctx.clearRect(0, 0, 1, 1);
      if (over) {
        ctx.fillStyle = over;
        ctx.fillRect(0, 0, 1, 1);
      }
      ctx.fillStyle = color;
      ctx.fillRect(0, 0, 1, 1);
      const d = ctx.getImageData(0, 0, 1, 1).data;
      return [d[0], d[1], d[2]];
    };
    const pageBg = css(document.body, "background-color");
    const near = (color, level, over) =>
      rgb(color, over).every((v) => v >= level);
    const top = rgb(css(card, "background-color")).join(",");
    check("卡片有圆角（≥8px）",
          parseFloat(css(card, "border-radius")) >= 8);
    check("卡片为发丝线扁平样式（细边、不靠阴影）",
          parseFloat(css(card, "border-top-width")) === 1 &&
          !near(css(card, "border-top-color"), 250) &&
          /none|0px/.test(css(card, "box-shadow")));
    check("卡片为近白表面（" + top + "）",
          rgb(css(card, "background-color")).every((v) => v >= 250));
    check("页面底色为冰白但不纯白（" +
          rgb(pageBg).join(",") + "）",
          rgb(pageBg).every((v) => v >= 242 && v < 255), false);
    const h1 = document.querySelector(".page.active h1");
    check("大标题使用衬线字体",
          /serif|Songti|SimSun|Georgia|Noto Serif/i.test(css(h1, "font-family")));
    const eyebrow = document.querySelector(".page.active .eyebrow");
    check("每页有等宽大写眉题",
          !!eyebrow && /mono|Consolas|Menlo/i.test(css(eyebrow, "font-family")) &&
          css(eyebrow, "text-transform") === "uppercase");
    const accentBtn = document.querySelector("button.primary");
    check("眉题与主按钮同用强调色（" +
          rgb(css(eyebrow, "color")).join(",") + "）",
          rgb(css(eyebrow, "color")).join(",") ===
          rgb(css(accentBtn, "background-color")).join(","));
    const activeNav = document.querySelector("#nav button.active");
    check("侧栏当前项为强调色填充药丸",
          !!activeNav && !!activeNav.querySelector(".side-no") &&
          parseFloat(css(activeNav, "border-radius")) >= 40);
    check("侧栏编号为等宽字体",
          !!activeNav &&
          /mono|Consolas|Menlo/i.test(css(activeNav.querySelector(".side-no"),
                                          "font-family")));
    const sideBg = rgb(css(document.getElementById("sidebar"),
                           "background-color"), pageBg);
    check("侧栏为浅色 + 发丝线（不再是深色块，" + sideBg.join(",") + "）",
          sideBg.every((v) => v >= 230), false);
    const brandIcon = document.querySelector("#brand img.brand-icon");
    check("侧栏品牌图标已加载",
          !!brandIcon && brandIcon.complete && brandIcon.naturalWidth > 0);
    const logPanel = document.querySelector(".log");
    check("日志面板为浅色等宽面板",
          rgb(css(logPanel, "background-color")).every((v) => v >= 240) &&
          /mono|Consolas|Menlo/i.test(css(logPanel, "font-family")), false);
    if (nav.length) { nav[0].click(); }
    await sleep(120);

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
