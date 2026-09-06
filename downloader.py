"""
downloader：Kittens Game 源码包下载器（纯逻辑，无 GUI 依赖）。

- 仓库：作者原版 nuclear-unicorn/kittensgame（bloodrizer 官方重定向）；
        社区版 kitten-science/kittensgame
- 版本：分支（main/master）或 GitHub release 标签
- 下载源：GitHub 直连，或镜像前缀（ghproxy.net / ghfast.top / gh-proxy.com）
- 流程：下载 zip 到 目标目录/.temp → 解压并“摊平”到目标目录根
  （消除“解压后嵌套一层 仓库-main/”的情况）→ 校验 index.html 存在
  → 清理 .temp
"""

import json
import os
import shutil
import urllib.error
import urllib.parse
import urllib.request
import zipfile

USER_AGENT = "Mozilla/5.0 (KGSaveManager)"

REPOS = {
    "author": {"owner": "nuclear-unicorn", "repo": "kittensgame"},
    "community": {"owner": "kitten-science", "repo": "kittensgame"},
}

# 下载源：空串 = GitHub 官网直连；其余为镜像前缀
MIRRORS = {
    "github.com": "",
    "ghproxy.net": "https://mirror.ghproxy.com/",
    "ghfast.top": "https://ghfast.top/",
    "gh-proxy.com": "https://gh-proxy.com/",
}


class DownloadCancelled(Exception):
    pass


class DownloadError(Exception):
    pass


def _http_json(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def list_versions(owner, repo):
    """返回可用版本 [(kind, label, ref)]——只列“真正可玩”的选择。

    两仓库都没有像样的 release；开发分支（dev/chore/experimental/feature/
    dependabot…）不是可玩版本，全部不列出。这里只提供：
    - 仓库默认分支（一般是 main，即最新版）；
    - 真实存在的 release 标签（若有）。
    """
    items = []
    default_branch = "main"
    try:
        info = _http_json(f"https://api.github.com/repos/{owner}/{repo}")
        db = info.get("default_branch")
        if db:
            default_branch = db
    except Exception:
        pass
    items.append(("branch", default_branch,
                  f"refs/heads/{default_branch}"))
    try:
        rels = _http_json(
            f"https://api.github.com/repos/{owner}/{repo}/releases",
            timeout=15) or []
        for rel in rels[:30]:
            tag = rel.get("tag_name")
            if tag:
                items.append(("tag", tag, f"refs/tags/{tag}"))
    except Exception:
        pass
    return items


def zip_url(owner, repo, ref):
    return f"https://github.com/{owner}/{repo}/archive/{ref}.zip"


def make_url(mirror_prefix, full_url):
    return mirror_prefix + full_url if mirror_prefix else full_url


def download_to(url, dest_path, progress=None, cancel=None,
                timeout=60):
    """流式下载到 dest_path。

    progress: 回调 (downloaded_bytes, total_bytes_or_None)
    cancel:   可调用返回 True 表示取消
    """
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        raise DownloadError(f"HTTP {e.code}")
    except urllib.error.URLError as e:
        raise DownloadError(str(e.reason))
    total = int(resp.headers.get("Content-Length") or 0) or None
    done = 0
    tmp = dest_path + ".part"
    try:
        with open(tmp, "wb") as fh:
            while True:
                if cancel is not None and cancel():
                    raise DownloadCancelled()
                chunk = resp.read(65536)
                if not chunk:
                    break
                fh.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
        os.replace(tmp, dest_path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _flatten_extract(zip_path, target_dir):
    """解压并把“单一顶层目录”摊平到 target_dir 根。"""
    with zipfile.ZipFile(zip_path) as zf:
        names = [n for n in zf.namelist() if not n.endswith("/")]
        if not names:
            raise DownloadError("zip 为空")
        # 找公共顶层前缀（形如 repo-main/）
        tops = {n.split("/", 1)[0] for n in names}
        prefix = None
        if len(tops) == 1:
            top = tops.pop()
            if "/" in next(iter([n for n in names])) and \
                    all(n.startswith(top + "/") for n in names):
                prefix = top + "/"
        for n in names:
            rel = n[len(prefix):] if prefix else n
            if not rel:
                continue
            dest = os.path.join(target_dir, rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with zf.open(n) as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out)


def install_game(repo_key, mirror, ref, target_dir, progress=None,
                 cancel=None):
    """一键下载+解压+摊平到 target_dir（清空旧内容）。

    :return: (最终游戏目录, 是否已设置) 仅目录即可
    """
    owner = REPOS[repo_key]["owner"]
    repo = REPOS[repo_key]["repo"]
    target_dir = os.path.abspath(target_dir)
    staging = os.path.join(target_dir, ".temp")
    os.makedirs(staging, exist_ok=True)

    full = zip_url(owner, repo, ref)
    url = make_url(MIRRORS.get(mirror, mirror), full)
    zip_path = os.path.join(staging, "game.zip")
    if progress:
        progress(0, None, f"url:{url}")
    download_to(url, zip_path, progress=progress, cancel=cancel)

    # 清空目标（首次确认已由调用方完成）
    for name in os.listdir(target_dir):
        p = os.path.join(target_dir, name)
        if name == ".temp":
            continue
        if os.path.isdir(p) and not os.path.islink(p):
            shutil.rmtree(p, ignore_errors=True)
        else:
            try:
                os.remove(p)
            except OSError:
                pass

    if progress:
        progress(0, None, "extract")
    _flatten_extract(zip_path, target_dir)

    if not os.path.isfile(os.path.join(target_dir, "index.html")):
        raise DownloadError("index.html missing after extraction")

    # 清理临时目录
    shutil.rmtree(staging, ignore_errors=True)
    return target_dir
