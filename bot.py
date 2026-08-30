import requests
from bs4 import BeautifulSoup
import os
import json
from datetime import datetime


WEBHOOK = os.getenv("DISCORD_WEBHOOK")
url = "https://concretejungle.forumactif.com/f11-roll-call"
headers = {
    "User-Agent": "Mozilla/5.0"
}


r = requests.get(url, headers=headers)
soup = BeautifulSoup(r.text, "html.parser")
topics = soup.select("a.topictitle")


try:
    with open("posted.json", "r") as f:
        posted = json.load(f)
except:
    posted = []


new_posts = []

for topic in topics:
    try:
        title = topic.text.strip()
        link = "https://concretejungle.forumactif.com" + topic["href"]

        if link not in posted:
            new_posts.append({
                "title": title,
                "link": link
            })

    except:
        continue


for post in reversed(new_posts):
    today = datetime.utcnow().strftime("%d %B %Y")

    data = {
        "content": "📢 @everyone",
        "embeds": [
            {
                "title": f"⭐ {post['title']}",
                "url": post["link"],
                "description": (
                    "Un nouveau visage vient d'apparaître "
                    "dans les rues de Londres...\n"
                    "Venez lui souhaiter la bienvenue ! 🎉"
                ),
                "color": 8145087,
                "fields": [
                    {
                        "name": "Serveur",
                        "value": "Concrete Jungle",
                        "inline": True
                    },
                    {
                        "name": "Postée le",
                        "value": today,
                        "inline": True
                    }
                ],
                "footer": {
                    "text": "Concrete Jungle — Bot de bienvenue"
                }
            }
        ]
    }

    requests.post(WEBHOOK, json=data)
    posted.append(post["link"])


with open("posted.json", "w") as f:
    json.dump(posted, f)
