
import requests
from bs4 import BeautifulSoup
import os
import json
from datetime import datetime


WEBHOOKS = [
    os.getenv("DISCORD_WEBHOOK"),
    os.getenv("DISCORD_WEBHOOK2")
]

WEBHOOKS = [webhook for webhook in WEBHOOKS if webhook]

url = "https://concretejungle.forumactif.com/f11-roll-call"
headers = {
    "User-Agent": "Mozilla/5.0"
}


r = requests.get(url, headers=headers)
r.raise_for_status()

soup = BeautifulSoup(r.text, "html.parser")
topics = soup.select("a.topictitle")


try:
    with open("posted.json", "r") as f:
        posted = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
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

    except (KeyError, TypeError):
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

    all_sent = True

    for webhook in WEBHOOKS:
        try:
            response = requests.post(
                webhook,
                json=data,
                timeout=15
            )
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"Erreur lors de l'envoi Discord : {e}")
            all_sent = False

    if all_sent and WEBHOOKS:
        posted.append(post["link"])


with open("posted.json", "w") as f:
    json.dump(posted, f)
