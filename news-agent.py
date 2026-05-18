"""
Fast 新闻速递 Agent — 每天早上9点推送新闻到手机
"""
import smtplib
import ssl
import json
import os
import urllib.request
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

# ====== 配置 ======
QQ_EMAIL = "2320978876@qq.com"
SMTP_CODE = os.environ.get("QQ_SMTP_CODE", "")
if not SMTP_CODE:
    print("错误：请先设置环境变量 QQ_SMTP_CODE")
    exit(1)


def fetch_news():
    """从多个免费源获取要闻，带跳转链接"""
    items = []

    # 微博热搜（免费 API）
    try:
        req = urllib.request.Request(
            "https://weibo.com/ajax/side/hotSearch",
            headers={"User-Agent": "Mozilla/5.0"}
        )
        data = json.loads(urllib.request.urlopen(req, timeout=10).read())
        for item in data.get("data", {}).get("realtime", [])[:10]:
            word = item.get("word", "")
            url = "https://s.weibo.com/weibo?q=" + urllib.request.quote(word)
            if word:
                items.append({"title": word, "url": url, "source": "微博热搜"})
    except Exception:
        pass

    # 知乎热榜
    try:
        req = urllib.request.Request(
            "https://api.zhihu.com/topstory/hot-lists/total?limit=10",
            headers={"User-Agent": "Mozilla/5.0"}
        )
        data = json.loads(urllib.request.urlopen(req, timeout=10).read())
        for item in data.get("data", [])[:5]:
            target = item.get("target", {})
            title = target.get("title", "")
            url = target.get("url", "")
            if title:
                items.append({"title": title, "url": url, "source": "知乎热榜"})
    except Exception:
        pass

    if not items:
        items.append({"title": "今日新闻源暂不可用，请稍后重试", "url": "", "source": ""})

    return items


def build_email_body(news_items):
    today = datetime.now().strftime("%Y年%m月%d日")
    source_colors = {"微博热搜": "#e0245e", "知乎热榜": "#0084ff"}

    cards = ""
    for i, item in enumerate(news_items, 1):
        src = item["source"]
        color = source_colors.get(src, "#666")
        badge = f"<span style='display:inline-block;background:{color};color:#fff;font-size:10px;padding:2px 8px;border-radius:10px;margin-left:8px;vertical-align:middle;'>{src}</span>" if src else ""

        if item["url"]:
            title_html = f"<a href='{item['url']}' style='color:#e0e0e0;text-decoration:none;font-size:15px;line-height:1.6;'>{item['title']}</a>"
        else:
            title_html = f"<span style='color:#e0e0e0;font-size:15px;'>{item['title']}</span>"

        cards += f"""
    <div style='background:#1e2d4a;border-radius:10px;padding:14px 16px;margin-bottom:10px;border-left:3px solid {color};'>
      <div style='display:flex;align-items:flex-start;gap:8px;'>
        <span style='color:{color};font-size:13px;font-weight:700;min-width:20px;padding-top:2px;'>#{i}</span>
        <div style='flex:1;'>
          {title_html}
          {badge}
        </div>
      </div>
    </div>"""

    return f"""<!DOCTYPE html>
<html><body style="font-family:'Microsoft YaHei',sans-serif;max-width:600px;margin:0 auto;padding:16px;background:#0f1923;">
<div style='text-align:center;padding:20px 0 10px;'>
  <div style='font-size:28px;font-weight:800;color:#e94560;letter-spacing:2px;'>FAST 早报</div>
  <div style='color:#5a7a9a;font-size:12px;margin-top:4px;'>{today} · 点击卡片跳转原文</div>
</div>
<div style='padding:0 4px;'>
  {cards}
</div>
<div style='text-align:center;padding:16px 0 4px;color:#3a4a5a;font-size:11px;'>
  Fast 管家自动推送 · 每日 9:00
</div>
</body></html>"""


def send_email(html_body):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Fast 早报 | {datetime.now().strftime('%m/%d')}"
    msg["From"] = QQ_EMAIL
    msg["To"] = QQ_EMAIL
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.qq.com", 465, context=context) as server:
        server.login(QQ_EMAIL, SMTP_CODE)
        server.sendmail(QQ_EMAIL, QQ_EMAIL, msg.as_string())


def main():
    print(f"[{datetime.now():%H:%M:%S}] Fast Agent 采集新闻...")
    news = fetch_news()
    print(f"  → {len(news)} 条资讯")

    body = build_email_body(news)
    send_email(body)

    print(f"  → 已发送 {QQ_EMAIL}")
    print(f"[{datetime.now():%H:%M:%S}] 完成")


if __name__ == "__main__":
    main()
