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

    // —— 小工具：切换页面、读计算样式（后面多处用到） ——
    const css = (el, prop) => getComputedStyle(el).getPropertyValue(prop);
    async function gotoTab(key) {
      for (const b of nav) {
        if (b.dataset.page === key) { b.click(); }
      }
      await sleep(120);
    }
    function columns(pageEl) {
      return getComputedStyle(pageEl).gridTemplateColumns
        .split(" ").filter((s) => s && s !== "none").length;
    }

    // 布局：宽屏横向分列 + 内容纵向滚动（不出现横向滚动条）
    const main = document.getElementById("main");
    const viewport = window.innerWidth;
    await gotoTab("kgsm");
    if (viewport >= 1180) {
      const cols = columns(document.querySelector(".page.active"));
      check("宽屏下卡片横向分列（" + cols + " 列）", cols >= 2);
    } else {
      check("窄窗口保持单列（" + viewport + "px）",
            columns(document.querySelector(".page.active")) === 1, false);
    }
    check("页面不出现横向滚动",
          document.documentElement.scrollWidth <= viewport + 1);
    check("内容区自己纵向滚动（scrollHeight > clientHeight）",
          main.scrollHeight > main.clientHeight ||
          document.querySelectorAll(".page.active .card").length <= 2, false);

    // 上下排版：启动游戏 / 下载游戏 / 配置 / 修改存档都是单列
    for (const key of ["game", "download", "settings", "editor"]) {
      await gotoTab(key);
      const tabBtn = Array.from(nav).find((b) => b.dataset.page === key);
      const label = tabBtn && tabBtn.lastElementChild
        ? tabBtn.lastElementChild.textContent : key;
      check("「" + label + "」页为上下单列排版",
            columns(document.getElementById("page-" + key)) === 1);
    }

    // 存档管理页：横向工具条 + 表格 + 日志
    await gotoTab("saves");
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
    // 功能按钮是横向排列的工具条（像顶部菜单栏），且没有"默认选中"样式
    const toolbar = document.querySelector("#page-saves .toolbar");
    const tbBtns = toolbar ? Array.from(toolbar.querySelectorAll("button")) : [];
    check("功能按钮为横向工具条（" + tbBtns.length + " 个）",
          !!toolbar && tbBtns.length >= 6 &&
          new Set(tbBtns.map((b) => Math.round(b.getBoundingClientRect().top)))
            .size === 1);
    check("功能按钮没有默认高亮项",
          !tbBtns.some((b) => b.classList.contains("primary")), false);
    check("使用说明板块已移除",
          !document.querySelector("#page-saves .hint"), false);

    // KGSM 页：引导顺序、无分割线、关于板块纵向链接
    await gotoTab("kgsm");
    const guideFirst = document.querySelector("#page-kgsm .guide li button");
    check("新手引导第一条是离线文档",
          !!guideFirst && guideFirst.dataset.action === "doc");
    const guideItems = Array.from(
      document.querySelectorAll("#page-kgsm .guide li"));
    check("引导列表项之间没有分割线",
          guideItems.every((li) =>
            parseFloat(css(li, "border-top-width")) === 0), false);
    check("关于板块链接纵向排列",
          getComputedStyle(document.querySelector("#page-kgsm .link-list"))
            .flexDirection === "column", false);
    check("文档入口已从侧栏移到关于板块",
          !document.getElementById("btn-doc") &&
          !!document.querySelector('#page-kgsm [data-action="doc"]'));

    // 路径文本必须能换行（不溢出、不被截断）
    await gotoTab("settings");    const pathNodes = [document.getElementById("about-paths"),
                       document.getElementById("set-hint"),
                       document.getElementById("server-status")];
    const overflowing = pathNodes.filter((el) => el && el.scrollWidth >
                                              el.clientWidth + 1);
    check("路径文本自动换行（无溢出的元素）", overflowing.length === 0, false);

    // 导航选中态有过渡动画（背景层 + 颜色）
    const navBtn = document.querySelector("#nav button");
    const dur = parseFloat(css(navBtn, "transition-duration")) || 0;
    const layer = getComputedStyle(navBtn, "::before");
    check("导航选中态有过渡动画", dur > 0 &&
          (parseFloat(layer.transitionDuration) || 0) > 0);

    // 退出按钮与弹窗：名字是"退出"，且不该出现复制路径按钮
    const exitBtn = document.getElementById("btn-exit");
    check("侧栏退出按钮叫「退出」",
          !!exitBtn && exitBtn.textContent.indexOf(
            state.strings["msg.btn_exit"] || "退出") === 0, false);
    exitBtn.click();
    await sleep(200);
    const modalTitle = document.getElementById("modal-title");
    const modalCopy = document.getElementById("modal-copy");
    const modalFile = document.getElementById("modal-file");
    const modalInput = document.getElementById("modal-input");
    const modalArea = document.getElementById("modal-text");
    check("退出确认弹窗只显示必要的控件（无复制路径/文件/输入框）",
          !document.getElementById("modal").hidden &&
          modalCopy.getClientRects().length === 0 &&
          modalFile.getClientRects().length === 0 &&
          modalInput.getClientRects().length === 0 &&
          modalArea.getClientRects().length === 0);
    check("退出弹窗标题为程序名",
          (modalTitle.textContent || "") ===
          (state.name || "KGSaveManager"), false);
    document.getElementById("modal-cancel").click();
    await sleep(120);
    check("取消退出后弹窗关闭", document.getElementById("modal").hidden);

    // 配置页：改完即存，不再有写入按钮
    await gotoTab("settings");
    check("配置页没有写入按钮",
          !document.querySelector('#page-settings [data-action="save-settings"]'));
    check("配置页提示为自动保存",
          (document.getElementById("set-hint").textContent || "")
            .indexOf((state.strings["st.hint"] || "").split("{")[0]) >= 0,
          false);
    // 只观察是否发出了 set_config（值不变，所以不会改动真实配置）
    const seenMethods = [];
    const realFetch = window.fetch;
    window.fetch = (url, opts) => {
      if (String(url).indexOf("/api/call") >= 0 && opts && opts.body) {
        try { seenMethods.push(JSON.parse(opts.body).method); } catch (e) {}
      }
      return realFetch(url, opts);
    };
    const portInput = document.getElementById("set-port");
    portInput.dispatchEvent(new Event("change"));
    await sleep(800);
    window.fetch = realFetch;
    check("配置改动触发自动保存（set_config）",
          seenMethods.indexOf("set_config") >= 0);

    // 关于板块：离线文档 + 更新日志两个入口（只在首页）
    await gotoTab("kgsm");
    const docs = Array.from(
      document.querySelectorAll('#page-kgsm .link-list [data-action="doc"]'));
    check("关于板块有离线文档与更新日志入口（" + docs.length + " 个）",
          docs.length === 2 &&
          docs[0].dataset.doc === "guide" &&
          docs[1].dataset.doc === "changelog");
    check("配置页不再重复放文档入口/关于标题",
          document.querySelectorAll('#page-settings [data-action="doc"]')
            .length === 0 &&
          !Array.from(document.querySelectorAll("#page-settings h2"))
            .some((h) => h.textContent === (state.strings["st.about"] || "关于")),
          false);

    // 槽位列表与下拉框使用同一格式（存档NN-名字）
    await gotoTab("saves");
    const firstCell = document.querySelector("#slot-rows tr td:nth-child(2)");
    const firstOption = document.querySelector("#set-home-slot option");
    check("槽位显示与下拉框同格式且用短横杠（" +
          (firstCell ? firstCell.textContent : "") + "）",
          !!firstCell && /^\S+\d{2}-/.test(firstCell.textContent) &&
          !!firstOption && /^\S+\d{2}-/.test(firstOption.textContent) &&
          firstCell.textContent.indexOf(" · ") < 0);

    // 下载页两个复选框：各自与所属文字首行对齐；同一行时顶端必须齐平
    // （曾因 .form label 覆盖 .check 变成 block + 外边距而"高低肩"）
    await gotoTab("download");
    const checkLabels = Array.from(
      document.querySelectorAll("#page-download .check"));
    const boxInfo = checkLabels.map((lab) => {
      const box = lab.querySelector("input").getBoundingClientRect();
      const labRect = lab.getBoundingClientRect();
      return { display: getComputedStyle(lab).display,
               top: Math.round(box.top), left: Math.round(box.left),
               labelTop: Math.round(labRect.top) };
    });
    const alignedToText = boxInfo.every(
      (b) => Math.abs(b.top - (b.labelTop + 3)) <= 6);
    const sameRow = boxInfo.length === 2 &&
      Math.abs(boxInfo[0].labelTop - boxInfo[1].labelTop) <= 1;
    const evenOnRow = !sameRow ||
      Math.abs(boxInfo[0].top - boxInfo[1].top) <= 1;
    check("下载页复选框不\"高低肩\"（顶端 " +
          boxInfo.map((b) => b.top).join(" / ") + "，标签顶端 " +
          boxInfo.map((b) => b.labelTop).join(" / ") + "）",
          alignedToText && evenOnRow);
    check("复选框标签用 flex 排布（" +
          boxInfo.map((b) => b.display).join(" / ") + "）",
          boxInfo.every((b) => b.display === "flex"), false);
    // 复选框行上下间距要均衡（曾出现上方 0、下方 22 的"上对齐"观感）
    const dlCard = document.querySelector("#page-download .card.form");
    const dlRows = Array.from(dlCard.children).filter(
      (el) => el.classList.contains("row") || el.tagName === "PROGRESS");
    const checkRow = dlCard.querySelector(".check-row");
    const nextEl = checkRow ? checkRow.nextElementSibling : null;
    const prevEl = checkRow ? checkRow.previousElementSibling : null;
    if (checkRow && nextEl && prevEl) {
      const gapAbove = Math.round(checkRow.getBoundingClientRect().top -
                                  prevEl.getBoundingClientRect().bottom);
      const gapBelow = Math.round(nextEl.getBoundingClientRect().top -
                                 checkRow.getBoundingClientRect().bottom);
      check("复选框行上下间距均衡（上 " + gapAbove + "px / 下 " +
            gapBelow + "px）", Math.abs(gapAbove - gapBelow) <= 4);
    } else {
      check("下载页复选框行结构完整", !!checkRow && !!nextEl, false);
    }
    // 下拉框箭头右侧要有间距（原生箭头贴边，已改为自绘箭头 + 右侧内边距）
    const sel = document.getElementById("dl-mirror");
    const selStyle = getComputedStyle(sel);
    const padRight = parseFloat(selStyle.paddingRight);
    check("下拉框右侧留出箭头间距（padding-right " + padRight + "px）",
          selStyle.appearance === "none" && padRight >= 30);
    void dlRows;

    // 修改存档页：视图/源码在左、打开/写入在右，且可折叠
    await gotoTab("editor");
    const edBar = document.querySelector("#page-editor .toolbar.split");
    const segBtns = Array.from(
      document.querySelectorAll("#page-editor .seg-group .seg"));
    const openBtn = document.querySelector('#page-editor [data-action="editor-open"]');
    check("编辑器工具条分左右两组",
          !!edBar && !!openBtn &&
          openBtn.getBoundingClientRect().left >
          segBtns[0].getBoundingClientRect().left, false);
    check("视图/源码为分段开关且有选中态",
          segBtns.length === 2 &&
          segBtns.filter((b) => b.classList.contains("active")).length === 1);
    check("默认选中「视图」", segBtns[0].classList.contains("active"));

    // 折叠功能的默认状态：只展开根节点，其余全部收起
    // （每次点击后 DOM 会整体重建，所以每次都要重新查询节点，不能用旧引用）
    const treeBranches = () => Array.from(
      document.querySelectorAll("#ed-tree-wrap .tree li.branch"));
    const visibleNodes = () => Array.from(
      document.querySelectorAll("#ed-tree-wrap .tree li"))
      .filter((li) => li.getClientRects().length > 0).length;
    const clickToggle = async (el) => {
      el.querySelector(".toggle").click();
      await sleep(90);
    };
    const branches = treeBranches();
    const expandedBranches = branches.filter(
      (li) => !li.classList.contains("collapsed"));
    const collapsedCount = branches.length - expandedBranches.length;
    check("默认只展开根那一层（分支 " + branches.length + " 个，收起 " +
          collapsedCount + " 个；节点 " +
          document.querySelectorAll("#ed-tree-wrap .tree li").length +
          " 个，可见 " + visibleNodes() + " 个）",
          branches.length >= 3 && expandedBranches.length === 2 &&
          expandedBranches[0] === branches[0] &&
          expandedBranches[1] === branches[1]);
    void collapsedCount;

    // 展开一个非根分支 → 可见节点变多；再收起 → 回到原样
    if (branches.length >= 3) {
      const base = visibleNodes();
      await clickToggle(treeBranches()[2]);
      const expanded = visibleNodes();
      await clickToggle(treeBranches()[2]);
      const restored = visibleNodes();
      check("非根分支可展开/收起（可见节点 " + base + " → " + expanded +
            " → " + restored + "）",
            expanded > base && restored === base);
    }

    // 根节点收起 → 只剩根自己；再展开 → 回到原样
    const rootBefore = visibleNodes();
    await clickToggle(treeBranches()[0]);
    const rootCollapsed = visibleNodes();
    await clickToggle(treeBranches()[0]);
    const rootRestored = visibleNodes();
    check("根节点可收起/展开（可见节点 " + rootBefore + " → " + rootCollapsed +
          " → " + rootRestored + "）",
          rootCollapsed === 1 && rootRestored === rootBefore);

    // 新样式是否真的生效（计算值，不看截图）
    await gotoTab("saves");
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
    const h1 = document.querySelector("#page-kgsm h1");
    check("首页保留衬线大标题",
          !!h1 && /serif|Songti|SimSun|Georgia|Noto Serif/i.test(
            css(h1, "font-family")));
    const extraH1 = ["game", "saves", "editor", "download", "settings"]
      .filter((key) => document.querySelector("#page-" + key + " h1"));
    check("其余页面只有眉题、没有重复大标题（多余 " + extraH1.length + " 个）",
          extraH1.length === 0);
    const eyebrow = document.querySelector(".page.active .eyebrow");
    check("每页有等宽大写眉题",
          !!eyebrow && /mono|Consolas|Menlo/i.test(css(eyebrow, "font-family")) &&
          css(eyebrow, "text-transform") === "uppercase");
    const accentBtn = document.querySelector("button.primary");
    const relLum = (c) => {
      const f = (v) => {
        const x = v / 255;
        return x <= 0.04045 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4);
      };
      return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]);
    };
    const contrast = (a, b) => {
      const la = relLum(a);
      const lb = relLum(b);
      const hi = Math.max(la, lb);
      const lo = Math.min(la, lb);
      return (hi + 0.05) / (lo + 0.05);
    };
    const fillRgb = rgb(css(accentBtn, "background-color"));
    const eyebrowRgb = rgb(css(eyebrow, "color"));
    check("按钮填充比眉题文字色更浅（" + fillRgb.join(",") + " vs " +
          eyebrowRgb.join(",") + "）",
          relLum(fillRgb) > relLum(eyebrowRgb));
    check("白字在按钮填充上仍达 AA（" +
          contrast([255, 255, 255], fillRgb).toFixed(2) + ":1）",
          contrast([255, 255, 255], fillRgb) >= 4.5);    const activeNav = document.querySelector("#nav button.active");
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
    const px = (el, prop) => parseFloat(css(el, prop));
    const bodyFs = px(document.body, "font-size");
    const h1Fs = px(h1, "font-size");
    const eyebrowFs = px(eyebrow, "font-size");
    check("排版层级：h1 " + h1Fs + "px / 正文 " + bodyFs + "px / 眉题 " +
          eyebrowFs + "px",
          h1Fs >= 24 && h1Fs / bodyFs >= 1.6 && eyebrowFs <= 13);
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
