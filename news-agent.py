"""
Fast AI 早报 Agent — 每天9点推送，AI专题 + 中文翻译
支持代理自动检测：有代理→国外一手源，无代理→国内源智能降级
代理未运行时自动拉起 FlClash
"""
import smtplib
import ssl
import json
import os
import re
import urllib.request
import xml.etree.ElementTree as ET
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import time
import subprocess
import socket

QQ_EMAIL = "2320978876@qq.com"
SMTP_CODE = os.environ.get("QQ_SMTP_CODE", "")
if not SMTP_CODE:
    print("错误：请先设置环境变量 QQ_SMTP_CODE")
    exit(1)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ── 代理自动拉起（安全加固版）──────────────────────────
# FlClash 安装路径
PROXY_APP_PATHS = [
    r"D:\Clash Party\FlClash\FlClash.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\FlClash\FlClash.exe"),
    os.path.expandvars(r"%USERPROFILE%\scoop\apps\clash-verge\current\clash-verge.exe"),
]

PROXY_PORT = 7890
PROXY_STARTUP_TIMEOUT = 20  # 最多等20秒
PROXY_VALIDATE_URL = "https://www.baidu.com"  # 验证代理真正可用

# PID 文件路径（记录脚本拉起的代理进程）
PROXY_PID_FILE = os.path.join(SCRIPT_DIR, ".proxy_pid")
# 安全锁：有这个文件则不自动拉起代理
NO_AUTO_PROXY_FILE = os.path.join(SCRIPT_DIR, ".no_auto_proxy")


def _get_pid_listening_on_port(port=PROXY_PORT):
    """返回监听指定端口的进程 PID，找不到返回 None"""
    try:
        result = subprocess.run(
            ["netstat", "-ano"], capture_output=True, text=True, timeout=3
        )
        for line in result.stdout.split("\n"):
            if f":{port}" in line and "LISTENING" in line:
                parts = line.strip().split()
                return int(parts[-1])
    except Exception:
        pass
    return None


def _kill_pid(pid):
    """安全地杀掉指定 PID 及其子进程"""
    if pid is None:
        return
    try:
        subprocess.run(
            ["taskkill", "/F", "/PID", str(pid), "/T"],
            capture_output=True, timeout=5,
        )
    except Exception:
        pass


def _find_clash_exe():
    """找到可用的 Clash 可执行文件"""
    for path in PROXY_APP_PATHS:
        if os.path.exists(path):
            return path
    return None


def _validate_proxy(proxy_url):
    """通过代理实际访问一个 URL，验证代理真正可用"""
    try:
        proxy_handler = urllib.request.ProxyHandler({
            "http": proxy_url, "https": proxy_url
        })
        opener = urllib.request.build_opener(proxy_handler)
        r = opener.open(PROXY_VALIDATE_URL, timeout=8)
        return r.getcode() == 200
    except Exception:
        return False


def _cleanup_stale_proxy():
    """
    清理上次脚本崩溃可能留下的僵尸代理进程。
    如果 .proxy_pid 文件存在，说明上次是脚本拉起的但没正常关闭，
    杀掉那个 PID。
    """
    if not os.path.exists(PROXY_PID_FILE):
        return
    try:
        with open(PROXY_PID_FILE, "r") as f:
            stale_pid = int(f.read().strip())
        # 检查这个 PID 是否还在运行且监听代理端口
        current_pid = _get_pid_listening_on_port()
        if current_pid and current_pid == stale_pid:
            print(f"  🧹 清理僵尸代理进程 PID={stale_pid}")
            _kill_pid(stale_pid)
            time.sleep(1)
    except (ValueError, OSError):
        pass
    try:
        os.remove(PROXY_PID_FILE)
    except OSError:
        pass


# 记录是否由脚本自己拉起的代理
_proxy_started_by_us = False
_proxy_pid = None


def start_proxy():
    """安全拉起代理。返回 (成功, 是否自己拉起的)"""
    global _proxy_started_by_us, _proxy_pid

    # 安全开关：如果 .no_auto_proxy 存在，绝不自动拉起
    if os.path.exists(NO_AUTO_PROXY_FILE):
        print(f"  ⛔ .no_auto_proxy 存在，跳过自动拉起")
        return False, False

    # 先清理可能存在的僵尸进程
    _cleanup_stale_proxy()

    # 检查代理是否已在运行且真正可用
    proxy_url = f"http://127.0.0.1:{PROXY_PORT}"
    if _validate_proxy(proxy_url):
        return True, False  # 已在运行且可用，不是我们拉起的

    # 端口开着但代理不可用 → 可能是僵尸，杀掉
    zombie_pid = _get_pid_listening_on_port()
    if zombie_pid:
        print(f"  ⚠️ 端口 {PROXY_PORT} 被占用但代理不可用，清理 PID={zombie_pid}")
        _kill_pid(zombie_pid)
        time.sleep(1)

    # 找不到 Clash 可执行文件
    clash_exe = _find_clash_exe()
    if not clash_exe:
        return False, False

    # 拉起
    print(f"  🔌 代理未运行，拉起: {clash_exe}")
    try:
        proc = subprocess.Popen(
            [clash_exe],
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW,
            close_fds=True,
        )
        # FlClash.exe 是启动器，实际代理是它拉起的子进程 FlClashCore.exe
        # 稍后我们会通过端口反查真正的代理 PID
    except Exception as e:
        print(f"  ⚠️ 拉起失败: {e}")
        return False, False

    # 等待端口就绪并验证代理可用
    for i in range(int(PROXY_STARTUP_TIMEOUT * 2)):
        time.sleep(0.5)
        if _validate_proxy(proxy_url):
            # 反查监听端口的真正 PID 并记录
            _proxy_pid = _get_pid_listening_on_port()
            if _proxy_pid:
                with open(PROXY_PID_FILE, "w") as f:
                    f.write(str(_proxy_pid))
            _proxy_started_by_us = True
            print(f"  ✅ 代理已就绪 (127.0.0.1:{PROXY_PORT}, PID={_proxy_pid})")
            return True, True

    # 超时：杀掉刚拉起的进程，避免留垃圾
    print(f"  ⚠️ 代理启动超时（{PROXY_STARTUP_TIMEOUT}s），回滚...")
    try:
        proc.kill()
    except Exception:
        pass
    return False, False


def stop_proxy():
    """仅关闭由脚本自己拉起的代理（精确杀 PID，不通杀）"""
    global _proxy_started_by_us, _proxy_pid

    if not _proxy_started_by_us:
        return  # 不是我们拉起的，不关

    print(f"  🔌 关闭代理 (PID={_proxy_pid})...")

    if _proxy_pid:
        _kill_pid(_proxy_pid)
        # 确认端口已释放
        for _ in range(10):
            time.sleep(0.3)
            if _get_pid_listening_on_port() is None:
                break

    # 清理 PID 文件
    try:
        os.remove(PROXY_PID_FILE)
    except OSError:
        pass

    _proxy_started_by_us = False
    _proxy_pid = None
    print(f"  ✅ 代理已关闭")


# ── 代理检测 ──────────────────────────────────────────
def get_proxy():
    """检测可用代理，返回 'http://host:port' 或 None"""

    # 如果代理不可用，尝试自动拉起
    proxy_url = f"http://127.0.0.1:{PROXY_PORT}"
    if not _validate_proxy(proxy_url):
        start_proxy()

    # 1. 环境变量
    for var in ("NEWS_PROXY", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        val = os.environ.get(var, "")
        if val:
            val = val.strip()
            if not val.startswith("http"):
                val = "http://" + val
            if _validate_proxy(val):
                return val

    # 2. 同目录 .proxy 文件
    proxy_file = os.path.join(SCRIPT_DIR, ".proxy")
    if os.path.exists(proxy_file):
        with open(proxy_file, "r") as f:
            val = f.read().strip()
            if val and not val.startswith("http"):
                val = "http://" + val
            if val and _validate_proxy(val):
                return val

    # 3. 扫描常见代理端口（验证真正可用）
    for host, port in [("127.0.0.1", p) for p in (7890, 7891, 10808, 10809, 1080, 8118, 4780, 7897)]:
        url = f"http://{host}:{port}"
        if _validate_proxy(url):
            return url

    return None



# ── 带代理的 urlopen ──────────────────────────────────
_proxy_opener = None

def smart_urlopen(url, timeout=10, headers=None):
    """智能 urlopen：有代理走代理，无代理直连"""
    global _proxy_opener
    if _proxy_opener is None:
        proxy = get_proxy()
        if proxy:
            _proxy_opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({"http": proxy, "https": proxy})
            )
        else:
            _proxy_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(url, headers=headers or {})
    if "User-Agent" not in req.headers:
        req.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    return _proxy_opener.open(req, timeout=timeout)


# ── 翻译 ──────────────────────────────────────────────
def translate_en_zh(text):
    """免费翻译 en→zh（MyMemory API），失败返回 None"""
    if not text or any('一' <= c <= '鿿' for c in text[:20]):
        return None
    try:
        t = text[:200]
        url = f"https://api.mymemory.translated.net/get?q={urllib.request.quote(t)}&langpair=en|zh&de=2320978876@qq.com"
        data = json.loads(smart_urlopen(url, timeout=5).read())
        result = data.get("responseData", {}).get("translatedText", "")
        if result and result != t and len(result) > 2:
            return result
    except Exception:
        pass
    return None


# ── 国外源（需代理）───────────────────────────────────
def fetch_github_trending():
    """GitHub AI 热门仓库"""
    items = []
    try:
        url = "https://api.github.com/search/repositories?q=AI+artificial-intelligence+created:>=" + \
              datetime.now().strftime("%Y-%m-") + "01&sort=stars&order=desc&per_page=8"
        data = json.loads(smart_urlopen(url, timeout=10, headers={
            "User-Agent": "FastAgent/1.0",
            "Accept": "application/vnd.github.v3+json"
        }).read())
        for repo in data.get("items", []):
            desc = repo.get("description") or ""
            zh = translate_en_zh(desc) if desc else None
            items.append({
                "title": f"{repo['full_name']} ⭐{repo['stargazers_count']}",
                "url": repo["html_url"],
                "source": "GitHub",
                "zh": zh or desc
            })
    except Exception:
        pass
    return items


def fetch_arxiv_ai():
    """arXiv AI 最新论文"""
    items = []
    try:
        url = "http://export.arxiv.org/api/query?search_query=cat:cs.AI&sortBy=submittedDate&sortOrder=descending&max_results=8"
        xml = smart_urlopen(url, timeout=15).read().decode("utf-8")
        entries = xml.split("<entry>")[1:]
        for entry in entries[:8]:
            ts = entry.find("<title>") + 7
            te = entry.find("</title>")
            if ts > 6 and te > ts:
                title = entry[ts:te].strip().replace("\n", " ").replace("  ", " ")
                is_ = entry.find("<id>") + 4
                ie = entry.find("</id>")
                arxiv_url = entry[is_:ie].strip() if is_ > 3 and ie > is_ else ""
                zh = translate_en_zh(title) if title else None
                items.append({
                    "title": title, "url": arxiv_url,
                    "source": "arXiv", "zh": zh or ""
                })
    except Exception:
        pass
    return items


RELEASE_KEYWORDS = [
    "发布", "推出", "上线", "开源", "开放", "上新", "升级",
    "launch", "release", "announce", "introducing", "unveil",
    "general availability", "preview", "now available",
    "gemini", "gpt-5", "gpt-4", "o3", "o4", "4.5", "4.7",
    "claude 4", "claude opus", "claude sonnet", "claude haiku",
    "deepseek", "qwen", "llama 4", "mistral",
    "veo", "sora", "imagen", "midjourney", "dall-e",
    "omni", "spark", "flash", "pro",
    "grok", "kimi", "豆包", "混元", "文心", "通义",
    "benchmark", "评测", "coding", "reasoning", "multimodal",
    "context window", "百万token", "参数",
]


def fetch_rss_feed(url, max_items=5):
    """通用 RSS 解析。返回 [{title, url, source}]，url 缺失时用 feed 主页兜底"""
    from urllib.parse import urlparse
    # 提取 feed 主页作为兜底链接
    parsed = urlparse(url)
    fallback_url = f"{parsed.scheme}://{parsed.netloc}"
    items = []
    try:
        raw = smart_urlopen(url, timeout=10).read().decode("utf-8", errors="replace")
        root = ET.fromstring(raw)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for item in root.iter("item"):
            if len(items) >= max_items:
                break
            title = item.findtext("title", "").strip()
            link = item.findtext("link", "").strip()
            if not link:
                alink = item.find("atom:link", ns)
                if alink is not None:
                    link = alink.get("href", "")
            if not link:
                # 尝试从 <guid> 中提取（RSS 有时把链接放 guid 里）
                guid = item.findtext("guid", "").strip()
                if guid and guid.startswith("http"):
                    link = guid
            if title:
                items.append({"title": title, "url": link or fallback_url, "source": ""})
        for entry in root.findall("atom:entry", ns) if root.tag.endswith("feed") else root.findall("{http://www.w3.org/2005/Atom}entry"):
            if len(items) >= max_items:
                break
            title = entry.findtext("atom:title", ns) or entry.findtext("{http://www.w3.org/2005/Atom}title", "").strip()
            link = ""
            for ln in entry.findall("atom:link", ns) + entry.findall("{http://www.w3.org/2005/Atom}link"):
                href = ln.get("href", "")
                if href:
                    link = href
                    break
            if title:
                items.append({"title": title, "url": link or fallback_url, "source": ""})
    except Exception:
        pass
    return items


def fetch_model_news():
    """模型动态：HN + 官方博客 RSS"""
    all_items = []
    seen = set()

    queries = [
        "Claude Anthropic model",
        "OpenAI GPT o3 o4",
        "Gemini Google model",
        "DeepSeek model",
        "Llama Meta open source",
    ]
    for q in queries:
        try:
            url = f"https://hn.algolia.com/api/v1/search_by_date?query=" + \
                  urllib.request.quote(q) + "&tags=story&hitsPerPage=3&numericFilters=created_at_i>" + \
                  str(int(datetime.now().timestamp()) - 7 * 86400)
            data = json.loads(smart_urlopen(url, timeout=5).read())
            for hit in data.get("hits", []):
                title = hit.get("title", "")
                hn_url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
                key = title[:80]
                if key in seen:
                    continue
                t = title.lower()
                if not any(kw.lower() in t for kw in RELEASE_KEYWORDS):
                    continue
                seen.add(key)
                zh = translate_en_zh(title)
                all_items.append({
                    "title": title, "url": hn_url,
                    "source": f"HN ⬆{hit.get('points',0)}",
                    "zh": zh if zh else "",
                })
        except Exception:
            pass

    feeds = [
        ("https://www.anthropic.com/blog/rss.xml", "Anthropic"),
        ("https://openai.com/blog/rss.xml", "OpenAI"),
        ("https://blog.google/technology/ai/rss/", "Google AI"),
    ]
    for url, source in feeds:
        for item in fetch_rss_feed(url, max_items=3):
            title = str(item.get("title", ""))
            t = title.lower()
            if not any(kw.lower() in t for kw in RELEASE_KEYWORDS):
                continue
            key = title[:80]
            if key not in seen:
                seen.add(key)
                item["source"] = source
                item["zh"] = translate_en_zh(title) if not any('一' <= c <= '鿿' for c in title[:5]) else ""
                all_items.append(item)

    return all_items[:8]


def fetch_general_news():
    """综合新闻：知乎 + 微博"""
    items = []
    try:
        url = "https://api.zhihu.com/topstory/hot-lists/total?limit=15"
        data = json.loads(smart_urlopen(url, timeout=10).read())
        for item in data.get("data", [])[:8]:
            t = item.get("target", {})
            title = t.get("title", "")
            url = t.get("url", "")
            if title:
                items.append({"title": title, "url": url, "source": "知乎"})
    except Exception:
        pass
    try:
        url = "https://weibo.com/ajax/side/hotSearch"
        data = json.loads(smart_urlopen(url, timeout=10).read())
        for item in data.get("data", {}).get("realtime", [])[:8]:
            word = item.get("word", "")
            url = "https://s.weibo.com/weibo?q=" + urllib.request.quote(word)
            if word:
                items.append({"title": word, "url": url, "source": "微博"})
    except Exception:
        pass
    return items


# ── 国内降级源（无需代理）────────────────────────────
# AI/科技关键词，用于从知乎热榜中筛选AI相关内容
AI_KEYWORDS_ZH = [
    "AI", "人工智能", "大模型", "GPT", "Claude",
    "OpenAI", "DeepSeek", "深度求索", "ChatGPT",
    "Gemini", "Llama", "Mistral", "Grok",
    "盘古", "华为", "百度", "文心", "阿里", "通义",
    "腾讯", "混元", "字节", "豆包", "月之暗面", "Kimi",
    "智谱", "百川", "零一", "Minimax",
    "自动驾驶", "机器人", "人形",
    "芯片", "GPU", "NVIDIA", "英伟达", "AMD",
    "量子", "spaceX", "星舰",
    "苹果", "Apple", "微软", "Microsoft", "Google", "谷歌",
    "Copilot", "Cursor", "AI", "agi", "llm",
    "transformer", "diffusion",
]

# 排除词：含这些词的条目不应被分类为AI
NOT_AI_KEYWORDS = [
    "世界杯", "足球", "NBA", "篮球", "奥运", "体育",
    "猫", "狗", "宠物", "食物", "美食", "小吃", "菜",
    "死刑", "判决", "法律", "法院", "判",
    "高考", "中考", "毕业",
    "房价", "楼市", "股市", "A股", "基金",
    "地震", "台风", "洪水", "灾害",
    "战争", "冲突", "和平", "制裁",
    "电影", "电视剧", "综艺", "明星", "演员", "歌手",
    "婚礼", "结婚", "恋爱", "出轨",
]

def classify_zhihu_item(title):
    """
    将知乎热榜条目分类：
    返回 'model' | 'trending' | 'paper' | 'general'
    """
    # 先排除明显非AI的内容
    if any(kw in title for kw in NOT_AI_KEYWORDS):
        return "general"

    t = title.lower()

    has_ai = any(kw.lower() in t for kw in AI_KEYWORDS_ZH)

    # 必须有AI/科技相关关键词才算AI板块
    if not has_ai:
        return "general"

    # 论文/研究类
    if any(kw in title for kw in ["论文", "研究", "Science", "Nature", "arXiv", "发现", "突破", "实验", "物理"]):
        return "paper"

    # AI 开源/项目/工具类
    if any(kw in title for kw in ["GitHub", "开源", "代码", "项目", "工具", "插件", "库", "框架", "平台"]):
        return "trending"

    # 产品发布/推出
    if any(kw in title for kw in ["发布", "推出", "上线", "开源", "上新", "公布", "亮相"]):
        return "model"

    # 其他AI/科技归为模型动态
    return "model"


def fetch_domestic_ai_sections():
    """
    从知乎热榜中智能提取，分成三个AI板块 + 综合
    返回四个列表: model_news, trending, papers, general
    """
    model_news = []
    trending = []
    papers = []
    general = []

    try:
        url = "https://api.zhihu.com/topstory/hot-lists/total?limit=20"
        data = json.loads(smart_urlopen(url, timeout=10).read())
        for item in data.get("data", []):
            t = item.get("target", {})
            title = t.get("title", "")
            item_url = t.get("url", "")
            if not title:
                continue

            category = classify_zhihu_item(title)
            entry = {"title": title, "url": item_url, "source": "知乎热榜"}

            if category == "model":
                model_news.append(entry)
            elif category == "trending":
                trending.append(entry)
            elif category == "paper":
                papers.append(entry)
            else:
                general.append(entry)
    except Exception:
        pass

    # 补充微博热榜到综合
    try:
        url = "https://weibo.com/ajax/side/hotSearch"
        data = json.loads(smart_urlopen(url, timeout=10).read())
        for item in data.get("data", {}).get("realtime", [])[:10]:
            word = item.get("word", "")
            wurl = "https://s.weibo.com/weibo?q=" + urllib.request.quote(word)
            if word:
                # 微博条目也尝试分类
                cat = classify_zhihu_item(word)
                entry = {"title": word, "url": wurl, "source": "微博"}
                if cat == "model" and len(model_news) < 6:
                    model_news.append(entry)
                elif cat == "trending" and len(trending) < 5:
                    trending.append(entry)
                elif cat == "paper" and len(papers) < 4:
                    papers.append(entry)
                elif len(general) < 10:
                    general.append(entry)
    except Exception:
        pass

    return model_news[:6], trending[:5], papers[:4], general[:10]


# ── 链接可靠性 ──────────────────────────────────────────
# 每个数据源的可信度等级
SOURCE_RELIABILITY = {
    "GitHub":    "⭐⭐⭐",
    "arXiv":     "⭐⭐⭐",
    "Anthropic": "⭐⭐⭐",
    "OpenAI":    "⭐⭐⭐",
    "Google AI": "⭐⭐⭐",
    "Hacker News": "⭐⭐",
    "知乎热榜":    "⭐⭐",
    "知乎":       "⭐⭐",
    "微博":       "⭐",
    "未知":       "⭐",
}

def check_url_alive(url, timeout=3):
    """快速 HEAD 检测链接是否可达（仅检测域名，跳转仍可信）"""
    if not url or not url.startswith("http"):
        return False
    try:
        req = urllib.request.Request(url, method="HEAD")
        req.headers["User-Agent"] = "FastAgent/1.0"
        urllib.request.urlopen(req, timeout=timeout)
        return True
    except Exception:
        return False  # HEAD 被拒不代表链接不可用，仅作参考


def ensure_url(title, url, fallback_source="baidu"):
    """确保每个条目都有可跳转链接"""
    if url and url.startswith("http"):
        return url
    # 兜底：生成搜索链接
    if fallback_source == "baidu":
        return "https://www.baidu.com/s?wd=" + urllib.request.quote(title)
    elif fallback_source == "google":
        return "https://www.google.com/search?q=" + urllib.request.quote(title)
    return "https://www.baidu.com/s?wd=" + urllib.request.quote(title)


# ── 邮件构建 ──────────────────────────────────────────
def build_email_body(sections):
    today = datetime.now().strftime("%Y年%m月%d日")
    colors = {
        "🧠 模型动态": "#ff9800",
        "🤖 AI 开源热榜": "#00d2ff",
        "📄 arXiv 最新论文": "#7c4dff",
        "📄 论文/研究": "#7c4dff",
        "🌐 综合新闻": "#e0245e",
    }

    cards = ""
    n = 0
    for sec_title, items in sections:
        if not items:
            continue
        color = colors.get(sec_title, "#666")
        cards += f"""
    <div style='margin:20px 0 10px;display:flex;align-items:center;gap:8px;'>
      <div style='width:4px;height:20px;background:{color};border-radius:2px;'></div>
      <span style='color:{color};font-size:16px;font-weight:700;'>{sec_title}</span>
      <span style='color:#3a4a5a;font-size:11px;'>{len(items)}条</span>
    </div>"""

        for item in items:
            n += 1
            src = item.get("source", "")
            title = item.get("title", "")
            url = ensure_url(title, item.get("url", ""))
            zh = item.get("zh", "")
            reliability = SOURCE_RELIABILITY.get(src, SOURCE_RELIABILITY["未知"])

            title_html = f"<a href='{url}' style='color:#d0d0d0;text-decoration:none;font-size:14px;line-height:1.6;' target='_blank' rel='noopener'>{title}</a>"
            zh_html = f"<div style='color:#78909c;font-size:12px;margin-top:3px;line-height:1.5;'>{zh}</div>" if zh else ""
            badge = f"<span style='display:inline-block;color:{color};font-size:10px;padding:2px 6px;border:1px solid {color};border-radius:8px;margin-left:6px;vertical-align:middle;white-space:nowrap;'>{src} {reliability}</span>" if src else ""

            cards += f"""
    <div style='background:#1a2838;border-radius:8px;padding:12px 14px;margin-bottom:6px;border-left:2px solid {color};'>
      <div style='display:flex;align-items:flex-start;gap:8px;'>
        <span style='color:{color};font-size:11px;font-weight:600;min-width:16px;padding-top:3px;'>#{n}</span>
        <div style='flex:1;min-width:0;'>
          {title_html}
          {zh_html}
          {badge}
        </div>
      </div>
    </div>"""

    return f"""<!DOCTYPE html>
<html><body style="font-family:'Microsoft YaHei',sans-serif;max-width:600px;margin:0 auto;padding:16px;background:#0f1923;">
<div style='text-align:center;padding:24px 0 12px;'>
  <div style='font-size:30px;font-weight:900;color:#e94560;letter-spacing:3px;'>FAST AI 早报</div>
  <div style='color:#5a7a9a;font-size:12px;margin-top:2px;'>{today} · 点击卡片跳转原文</div>
  <div style='color:#3a4a5a;font-size:11px;margin-top:1px;'>AI 前沿 × 综合资讯 · 共 {n} 条</div>
</div>
<div style='padding:0 2px;'>
  {cards}
</div>
<div style='text-align:center;padding:20px 0 6px;'>
  <div style='color:#3a4a5a;font-size:11px;'>Fast 管家自动推送 · 每日 9:00</div>
  <div style='color:#2a3a4a;font-size:10px;margin-top:2px;'>⭐⭐⭐ = 一手官方源 | ⭐⭐ = 知名聚合 | ⭐ = 社交热榜</div>
  <div style='color:#2a3a4a;font-size:10px;margin-top:1px;'>数据源：AI RSS · GitHub · arXiv · 知乎 · 微博</div>
</div>
</body></html>"""


def send_email(html_body):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Fast AI 早报 | {datetime.now().strftime('%m/%d')}"
    msg["From"] = QQ_EMAIL
    msg["To"] = QQ_EMAIL
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.qq.com", 465, context=ssl.create_default_context()) as s:
        s.login(QQ_EMAIL, SMTP_CODE)
        s.sendmail(QQ_EMAIL, QQ_EMAIL, msg.as_string())


# ── 防重复发送（加固版）────────────────────────────────
# 双锁机制：.last_sent 日期锁（永久）+ .sending 进程锁（临时120秒）
# .last_sent = 今天已发过 → 跳过（除非 --force）
# .sending   = 另一个进程正在发 → 跳过（超120秒自动清理）

def _safe_remove(path, label="file"):
    """安全删除文件，失败不报错"""
    try:
        os.remove(path)
        return True
    except (OSError, FileNotFoundError):
        return False


def check_already_sent():
    """检查今天是否已发送。返回 (已发送, 详情描述)"""
    marker = os.path.join(SCRIPT_DIR, ".last_sent")
    lockfile = os.path.join(SCRIPT_DIR, ".sending")
    today = datetime.now().strftime("%Y%m%d")

    # 先清理僵尸锁
    if os.path.exists(lockfile):
        age = time.time() - os.path.getmtime(lockfile)
        if age > 120:
            print(f"  🧹 清理僵尸锁（{int(age)}秒前残留）")
            _safe_remove(lockfile, "lockfile")

    # 检查组内是否有活跃的发送进程
    if os.path.exists(lockfile):
        age = time.time() - os.path.getmtime(lockfile)
        if age <= 120:
            return True, f"另一个发送进程活跃中（{int(age)}秒前启动）"

    # 检查日期锁
    if os.path.exists(marker):
        with open(marker, "r") as f:
            stored_date = f.read().strip()
        if stored_date == today:
            return True, f"今天({today})已发送过"

    return False, ""


def acquire_lock():
    """尝试获取发送锁。返回 True=成功获取"""
    lockfile = os.path.join(SCRIPT_DIR, ".sending")
    if os.path.exists(lockfile):
        age = time.time() - os.path.getmtime(lockfile)
        if age <= 120:
            return False  # 另一个进程正在发
        _safe_remove(lockfile, "lockfile")  # 清理超时锁
    with open(lockfile, "w") as f:
        f.write(datetime.now().isoformat())
    return True


def release_lock():
    _safe_remove(os.path.join(SCRIPT_DIR, ".sending"), "lock")


def mark_sent():
    """写入日期锁并确保立即落盘"""
    marker = os.path.join(SCRIPT_DIR, ".last_sent")
    today = datetime.now().strftime("%Y%m%d")
    with open(marker, "w") as f:
        f.write(today)
        f.flush()
        os.fsync(f.fileno())  # 确保写入磁盘
    print(f"  📌 日期锁已写入: {today}")


# ── 主逻辑 ────────────────────────────────────────────
def main():
    import sys as _sys
    dry_run = "--dry-run" in _sys.argv or "--dry" in _sys.argv
    force = "--force" in _sys.argv

    today_str = datetime.now().strftime("%Y年%m月%d日 %H:%M")
    already_sent, reason = check_already_sent()
    if already_sent and not force:
        print(f"[{today_str}] 跳过发送 — {reason}")
        print(f"  如需重发: python news-agent.py --force")
        return

    if not acquire_lock():
        print(f"[{datetime.now():%H:%M:%S}] 获取发送锁失败，可能有其他进程正在发送。")
        return

    proxy = get_proxy()
    proxy_status = f"代理 {proxy}" if proxy else "直连（无代理）"
    print(f"[{datetime.now():%H:%M:%S}] Fast AI Agent 采集新闻 ({proxy_status}){' (DRY-RUN)' if dry_run else ''}...")

    if proxy:
        # ── 代理可用：使用国外一手源 ──
        sections = [
            ("🧠 模型动态", fetch_model_news()),
            ("🤖 AI 开源热榜", fetch_github_trending()),
            ("📄 arXiv 最新论文", fetch_arxiv_ai()),
            ("🌐 综合新闻", fetch_general_news()),
        ]
    else:
        # ── 无代理：国内源智能降级 ──
        model_news, trending, papers, general = fetch_domestic_ai_sections()

        # 如果国内AI分类结果太少，补充知乎热榜全部条目到综合
        if not general:
            try:
                url = "https://api.zhihu.com/topstory/hot-lists/total?limit=15"
                data = json.loads(smart_urlopen(url, timeout=10).read())
                for item in data.get("data", []):
                    t = item.get("target", {})
                    title = t.get("title", "")
                    item_url = t.get("url", "")
                    if title:
                        general.append({"title": title, "url": item_url, "source": "知乎"})
            except Exception:
                pass

        sections = [
            ("🧠 模型动态", model_news),
            ("🤖 AI 开源热榜", trending),
            ("📄 论文/研究", papers),
            ("🌐 综合新闻", general),
        ]

    total = sum(len(items) for _, items in sections)
    print(f"  → 共 {total} 条资讯")

    if dry_run:
        print("\n  --- DRY-RUN 预览 ---")
        for sec_title, items in sections:
            print(f"\n  [{sec_title}] {len(items)} 条")
            for i, item in enumerate(items[:3]):
                print(f"    {i+1}. {item.get('title','')[:70]}")
        print(f"\n  [dry-run] 未发送邮件，共 {total} 条。")
        stop_proxy()
        return

    mark_sent()
    build = build_email_body(sections)
    send_email(build)
    release_lock()
    stop_proxy()

    print(f"  → 已发送 {QQ_EMAIL}")
    print(f"[{datetime.now():%H:%M:%S}] 完成")


if __name__ == "__main__":
    main()
