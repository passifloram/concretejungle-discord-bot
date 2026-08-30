import json
import os
import sys
from datetime import datetime
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup


# ==========================================================
# CONFIGURATION
# ==========================================================

FORUM_URL = "https://concretejungle.forumactif.com"
ROLL_CALL_URL = f"{FORUM_URL}/f11-roll-call"

POSTED_FILE = "posted.json"
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
}


# ==========================================================
# FONCTIONS
# ==========================================================

def normaliser_url(href):
    """
    Transforme une adresse relative en adresse complète et retire
    les ancres ainsi que les paramètres inutiles.
    """
    url = urljoin(FORUM_URL, href)
    morceaux = urlsplit(url)

    return urlunsplit((
        morceaux.scheme,
        morceaux.netloc,
        morceaux.path.rstrip("/"),
        "",
        ""
    ))


def charger_historique():
    """
    Charge les sujets déjà annoncés.
    """
    try:
        with open(POSTED_FILE, "r", encoding="utf-8") as fichier:
            contenu = json.load(fichier)

        if not isinstance(contenu, list):
            raise ValueError("posted.json ne contient pas une liste.")

        return list(dict.fromkeys(
            normaliser_url(url)
            for url in contenu
            if isinstance(url, str) and url.strip()
        ))

    except FileNotFoundError:
        print("posted.json absent : création d'un nouvel historique.")
        return []

    except (json.JSONDecodeError, ValueError) as erreur:
        print(f"Historique illisible : {erreur}")
        print("Le bot repart avec un historique vide.")
        return []


def enregistrer_historique(historique):
    """
    Enregistre les sujets annoncés dans posted.json.
    """
    with open(POSTED_FILE, "w", encoding="utf-8") as fichier:
        json.dump(
            historique,
            fichier,
            ensure_ascii=False,
            indent=2
        )


def recuperer_sujets():
    """
    Charge Roll Call et récupère les sujets visibles.
    """
    session = requests.Session()
    session.headers.update(HEADERS)

    print(f"Lecture de : {ROLL_CALL_URL}")

    reponse = session.get(
        ROLL_CALL_URL,
        timeout=30,
        allow_redirects=True
    )

    print(f"Statut Forumactif : {reponse.status_code}")
    print(f"URL finale : {reponse.url}")
    print(f"Taille de la page : {len(reponse.text)} caractères")

    reponse.raise_for_status()

    soup = BeautifulSoup(reponse.text, "html.parser")

    # Sélecteur habituel de Forumactif, avec quelques solutions
    # de secours si la structure HTML varie.
    liens = soup.select(
        "a.topictitle, "
        ".topicslist_row a[href*='/t'], "
        ".topic-title a[href*='/t'], "
        "a[href^='/t'][class*='topic']"
    )

    sujets = []
    urls_vues = set()

    for lien in liens:
        titre = lien.get_text(" ", strip=True)
        href = lien.get("href", "").strip()

        if not titre or not href:
            continue

        url = normaliser_url(href)

        # On conserve uniquement les véritables sujets du forum.
        if not url.startswith(f"{FORUM_URL}/t"):
            continue

        if url in urls_vues:
            continue

        urls_vues.add(url)

        sujets.append({
            "title": titre,
            "link": url
        })

    print(f"Nombre de sujets détectés : {len(sujets)}")

    for sujet in sujets:
        print(f"— {sujet['title']} : {sujet['link']}")

    if not sujets:
        titre_page = soup.title.get_text(" ", strip=True) if soup.title else "inconnu"

        print(f"Titre de la page reçue : {titre_page}")

        raise RuntimeError(
            "Aucun sujet n'a été détecté dans Roll Call. "
            "Forumactif a peut-être renvoyé une page de connexion, "
            "une protection anti-bot ou une structure HTML différente."
        )

    return sujets


def publier_sur_discord(sujet):
    """
    Publie un sujet sur Discord et vérifie réellement la réponse.
    """
    if not DISCORD_WEBHOOK:
        raise RuntimeError(
            "Le secret GitHub DISCORD_WEBHOOK est absent ou vide."
        )

    aujourd_hui = datetime.now().strftime("%d/%m/%Y")

    donnees = {
        "content": "📢 @everyone",
        "allowed_mentions": {
            "parse": ["everyone"]
        },
        "embeds": [
            {
                "title": f"⭐ {sujet['title']}",
                "url": sujet["link"],
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
                        "name": "Posté le",
                        "value": aujourd_hui,
                        "inline": True
                    }
                ],
                "footer": {
                    "text": "Concrete Jungle — Bot de bienvenue"
                }
            }
        ]
    }

    reponse = requests.post(
        DISCORD_WEBHOOK,
        json=donnees,
        timeout=30
    )

    print(
        f"Réponse Discord pour « {sujet['title']} » : "
        f"{reponse.status_code}"
    )

    if reponse.status_code not in (200, 204):
        raise RuntimeError(
            f"Discord a refusé le message : "
            f"{reponse.status_code} — {reponse.text[:500]}"
        )


# ==========================================================
# LANCEMENT DU BOT
# ==========================================================

def main():
    historique = charger_historique()
    deja_annonces = set(historique)

    sujets = recuperer_sujets()

    nouveaux_sujets = [
        sujet
        for sujet in sujets
        if sujet["link"] not in deja_annonces
    ]

    print(f"Nouveaux sujets à annoncer : {len(nouveaux_sujets)}")

    if not nouveaux_sujets:
        print("Aucune nouvelle annonce à publier.")
        return

    # reversed() permet d'envoyer les sujets du plus ancien au plus récent.
    for sujet in reversed(nouveaux_sujets):
        print(f"Publication de : {sujet['title']}")

        publier_sur_discord(sujet)

        # Le lien n'est enregistré qu'après confirmation de Discord.
        historique.append(sujet["link"])
        deja_annonces.add(sujet["link"])
        enregistrer_historique(historique)

        print(f"Annonce publiée : {sujet['link']}")

    print("Toutes les nouvelles annonces ont été publiées.")


if __name__ == "__main__":
    try:
        main()

    except Exception as erreur:
        print(f"ERREUR DU BOT : {erreur}", file=sys.stderr)
        sys.exit(1)
