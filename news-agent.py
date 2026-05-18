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
    rows = ""
    for i, item in enumerate(news_items, 1):
        tag = f"[{item['source']}]" if item["source"] else ""
        if item["url"]:
            row = f"{i}. {tag} <a href='{item['url']}' style='color:#4fc3f7;text-decoration:none;'>{item['title']}</a>"
        else:
            row = f"{i}. {tag} {item['title']}"
        rows += row + "\n                "

    return f"""<!DOCTYPE html>
<html><body style="font-family:'Microsoft YaHei',sans-serif;max-width:600px;margin:0 auto;padding:20px;background:#1a1a2e;color:#eee;">
<div style="background:#16213e;border-radius:12px;padding:24px;">
  <h2 style="color:#e94560;margin-top:0;">Fast 新闻速递</h2>
  <p style="color:#aaa;font-size:13px;">{today} 早间简报 · 点击标题跳转原文</p>
  <hr style="border-color:#333;margin:16px 0;">
  <div style="font-size:14px;line-height:2.2;color:#ccc;">
    {rows}
  </div>
  <hr style="border-color:#333;margin:16px 0;">
  <p style="color:#555;font-size:11px;text-align:center;">— Fast 管家自动推送 · 每天早上9点 —</p>
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
