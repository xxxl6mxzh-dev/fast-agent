"""
Fast 新闻速递 Agent — AI 聚焦版，每天早上9点推送到手机
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


def fetch_github_trending():
    """GitHub AI 热门仓库（免费 API，无需 key）"""
    items = []
    try:
        url = "https://api.github.com/search/repositories?q=AI+artificial-intelligence+created:>=" + \
              (datetime.now().strftime("%Y-%m-") + "01") + \
              "&sort=stars&order=desc&per_page=8"
        req = urllib.request.Request(url, headers={
            "User-Agent": "FastAgent/1.0",
            "Accept": "application/vnd.github.v3+json"
        })
        data = json.loads(urllib.request.urlopen(req, timeout=10).read())
        for repo in data.get("items", []):
            items.append({
                "title": f"{repo['full_name']} — ⭐{repo['stargazers_count']} {repo.get('description','')[:60]}",
                "url": repo["html_url"],
                "source": "GitHub AI"
            })
    except Exception:
        pass
    return items


def fetch_arxiv_ai():
    """arXiv AI 最新论文（免费 RSS）"""
    items = []
    try:
        url = "http://export.arxiv.org/api/query?search_query=cat:cs.AI&sortBy=submittedDate&sortOrder=descending&max_results=8"
        req = urllib.request.Request(url, headers={"User-Agent": "FastAgent/1.0"})
        xml = urllib.request.urlopen(req, timeout=15).read().decode("utf-8")
        entries = xml.split("<entry>")[1:]
        for entry in entries[:8]:
            title_start = entry.find("<title>") + 7
            title_end = entry.find("</title>")
            id_start = entry.find("<id>") + 4
            id_end = entry.find("</id>")
            if title_end > title_start and id_end > id_start:
                title = entry[title_start:title_end].strip().replace("\n", " ")
                arxiv_id = entry[id_start:id_end].strip()
                items.append({
                    "title": title[:120],
                    "url": arxiv_id.replace("abs", "abs"),
                    "source": "arXiv AI"
                })
    except Exception:
        pass
    return items


def fetch_general_news():
    """综合新闻：微博+知乎"""
    items = []

    # 知乎热榜
    try:
        req = urllib.request.Request(
            "https://api.zhihu.com/topstory/hot-lists/total?limit=15",
            headers={"User-Agent": "Mozilla/5.0"}
        )
        data = json.loads(urllib.request.urlopen(req, timeout=10).read())
        for item in data.get("data", [])[:8]:
            target = item.get("target", {})
            title = target.get("title", "")
            url = target.get("url", "")
            if title:
                items.append({"title": title, "url": url, "source": "知乎"})
    except Exception:
        pass

    # 微博热搜
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
    """卡片式排版，分 AI 板块 + 综合板块"""
    today = datetime.now().strftime("%Y年%m月%d日")
    section_colors = {
        "🤖 AI 开源热榜": "#00d2ff",
        "📄 arXiv 最新论文": "#7c4dff",
        "🌐 综合新闻": "#e0245e"
    }

    all_cards = ""
    global_count = 0

    for section_title, items in sections:
        if not items:
            continue
        color = section_colors.get(section_title, "#666")
        all_cards += f"""
    <div style='margin:20px 0 10px;display:flex;align-items:center;gap:8px;'>
      <div style='width:4px;height:20px;background:{color};border-radius:2px;'></div>
      <span style='color:{color};font-size:16px;font-weight:700;'>{section_title}</span>
      <span style='color:#3a4a5a;font-size:11px;'>{len(items)}条</span>
    </div>"""

        for item in items:
            global_count += 1
            src = item["source"]
            if item["url"]:
                title_html = f"<a href='{item['url']}' style='color:#d0d0d0;text-decoration:none;font-size:14px;line-height:1.6;'>{item['title']}</a>"
            else:
                title_html = f"<span style='color:#d0d0d0;font-size:14px;'>{item['title']}</span>"

            badge = f"<span style='display:inline-block;color:{color};font-size:10px;padding:2px 6px;border:1px solid {color};border-radius:8px;margin-left:6px;vertical-align:middle;white-space:nowrap;'>{src}</span>" if src else ""

            all_cards += f"""
    <div style='background:#1a2838;border-radius:8px;padding:12px 14px;margin-bottom:6px;border-left:2px solid {color};'>
      <div style='display:flex;align-items:flex-start;gap:8px;'>
        <span style='color:{color};font-size:11px;font-weight:600;min-width:16px;padding-top:3px;'>#{global_count}</span>
        <div style='flex:1;min-width:0;'>
          {title_html}
          {badge}
        </div>
      </div>
    </div>"""

    return f"""<!DOCTYPE html>
<html><body style="font-family:'Microsoft YaHei',sans-serif;max-width:600px;margin:0 auto;padding:16px;background:#0f1923;">
<div style='text-align:center;padding:24px 0 12px;'>
  <div style='font-size:30px;font-weight:900;color:#e94560;letter-spacing:3px;'>FAST AI 早报</div>
  <div style='color:#5a7a9a;font-size:12px;margin-top:2px;'>{today} · 点击卡片跳转原文</div>
  <div style='color:#3a4a5a;font-size:11px;margin-top:1px;'>AI 前沿 × 综合资讯 · 共 {global_count} 条</div>
</div>
<div style='padding:0 2px;'>
  {all_cards}
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

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.qq.com", 465, context=context) as server:
        server.login(QQ_EMAIL, SMTP_CODE)
        server.sendmail(QQ_EMAIL, QQ_EMAIL, msg.as_string())


def main():
    print(f"[{datetime.now():%H:%M:%S}] Fast AI Agent 采集新闻...")

    sections = [
        ("🤖 AI 开源热榜", fetch_github_trending()),
        ("📄 arXiv 最新论文", fetch_arxiv_ai()),
        ("🌐 综合新闻", fetch_general_news()),
    ]

    total = sum(len(items) for _, items in sections)
    print(f"  → 共 {total} 条资讯")

    body = build_email_body(sections)
    send_email(body)

    print(f"  → 已发送 {QQ_EMAIL}")
    print(f"[{datetime.now():%H:%M:%S}] 完成")


if __name__ == "__main__":
    main()
