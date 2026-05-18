"""
Fast AI 早报 Agent — 每天9点推送，AI专题 + 中文翻译
"""
import smtplib
import ssl
import json
import os
import urllib.request
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

QQ_EMAIL = "2320978876@qq.com"
SMTP_CODE = os.environ.get("QQ_SMTP_CODE", "")
if not SMTP_CODE:
    print("错误：请先设置环境变量 QQ_SMTP_CODE")
    exit(1)


def translate_en_zh(text):
    """免费翻译 en→zh（MyMemory API），失败返回 None"""
    if not text or any('一' <= c <= '鿿' for c in text[:20]):
        return None
    try:
        t = text[:200]
        url = f"https://api.mymemory.translated.net/get?q={urllib.request.quote(t)}&langpair=en|zh&de=fastagent"
        data = json.loads(urllib.request.urlopen(url, timeout=5).read())
        result = data.get("responseData", {}).get("translatedText", "")
        if result and result != t and len(result) > 2:
            return result
    except Exception:
        pass
    return None


def fetch_github_trending():
    """GitHub AI 热门仓库，附中文翻译"""
    items = []
    try:
        url = "https://api.github.com/search/repositories?q=AI+artificial-intelligence+created:>=" + \
              datetime.now().strftime("%Y-%m-") + "01&sort=stars&order=desc&per_page=8"
        req = urllib.request.Request(url, headers={
            "User-Agent": "FastAgent/1.0",
            "Accept": "application/vnd.github.v3+json"
        })
        data = json.loads(urllib.request.urlopen(req, timeout=10).read())
        for repo in data.get("items", []):
            desc = repo.get("description") or ""
            zh = translate_en_zh(desc) if desc else None
            items.append({
                "title": f"{repo['full_name']} ⭐{repo['stargazers_count']}",
                "url": repo["html_url"],
                "source": "GitHub AI",
                "zh": zh or desc
            })
    except Exception:
        pass
    return items


def fetch_arxiv_ai():
    """arXiv AI 最新论文，标题附中文翻译"""
    items = []
    try:
        url = "http://export.arxiv.org/api/query?search_query=cat:cs.AI&sortBy=submittedDate&sortOrder=descending&max_results=8"
        req = urllib.request.Request(url, headers={"User-Agent": "FastAgent/1.0"})
        xml = urllib.request.urlopen(req, timeout=15).read().decode("utf-8")
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
                    "title": title,
                    "url": arxiv_url,
                    "source": "arXiv AI",
                    "zh": zh or ""
                })
    except Exception:
        pass
    return items


def fetch_general_news():
    """综合新闻：知乎 + 微博"""
    items = []

    try:
        req = urllib.request.Request(
            "https://api.zhihu.com/topstory/hot-lists/total?limit=15",
            headers={"User-Agent": "Mozilla/5.0"}
        )
        data = json.loads(urllib.request.urlopen(req, timeout=10).read())
        for item in data.get("data", [])[:8]:
            t = item.get("target", {})
            title = t.get("title", "")
            url = t.get("url", "")
            if title:
                items.append({"title": title, "url": url, "source": "知乎"})
    except Exception:
        pass

    try:
        req = urllib.request.Request(
            "https://weibo.com/ajax/side/hotSearch",
            headers={"User-Agent": "Mozilla/5.0"}
        )
        data = json.loads(urllib.request.urlopen(req, timeout=10).read())
        for item in data.get("data", {}).get("realtime", [])[:8]:
            word = item.get("word", "")
            url = "https://s.weibo.com/weibo?q=" + urllib.request.quote(word)
            if word:
                items.append({"title": word, "url": url, "source": "微博"})
    except Exception:
        pass

    return items


def build_email_body(sections):
    today = datetime.now().strftime("%Y年%m月%d日")
    colors = {
        "🤖 AI 开源热榜": "#00d2ff",
        "📄 arXiv 最新论文": "#7c4dff",
        "🌐 综合新闻": "#e0245e"
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
            url = item.get("url", "")
            zh = item.get("zh", "")

            title_html = f"<a href='{url}' style='color:#d0d0d0;text-decoration:none;font-size:14px;line-height:1.6;'>{title}</a>" if url else f"<span style='color:#d0d0d0;font-size:14px;'>{title}</span>"
            zh_html = f"<div style='color:#78909c;font-size:12px;margin-top:3px;line-height:1.5;'>{zh}</div>" if zh else ""
            badge = f"<span style='display:inline-block;color:{color};font-size:10px;padding:2px 6px;border:1px solid {color};border-radius:8px;margin-left:6px;vertical-align:middle;white-space:nowrap;'>{src}</span>" if src else ""

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
  <div style='color:#2a3a4a;font-size:10px;margin-top:2px;'>数据源：GitHub · arXiv · 知乎 · 微博</div>
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


def main():
    print(f"[{datetime.now():%H:%M:%S}] Fast AI Agent 采集新闻...")

    sections = [
        ("🤖 AI 开源热榜", fetch_github_trending()),
        ("📄 arXiv 最新论文", fetch_arxiv_ai()),
        ("🌐 综合新闻", fetch_general_news()),
    ]

    total = sum(len(items) for _, items in sections)
    print(f"  → 共 {total} 条资讯")

    build = build_email_body(sections)
    send_email(build)

    print(f"  → 已发送 {QQ_EMAIL}")
    print(f"[{datetime.now():%H:%M:%S}] 完成")


if __name__ == "__main__":
    main()
