import json
import os
import re
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
# OUTILS POUR LES URL
# ==========================================================

def normaliser_url(href):
    """
    Transforme une URL relative en URL complète.
    Retire les paramètres et les ancres, notamment #12345.
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


def recuperer_id_sujet(url):
    """
    Extrait le numéro d'un sujet Forumactif.

    Exemples :
    /t2355-registre-technique-du-directory -> 2355
    /t2355p25-registre...                  -> 2355
    """
    correspondance = re.search(r"/t(\d+)", url)

    if not correspondance:
        return None

    return correspondance.group(1)


# ==========================================================
# HISTORIQUE DES SUJETS PUBLIÉS
# ==========================================================

def charger_historique():
    """
    Charge les URL déjà annoncées depuis posted.json.
    """
    try:
        with open(POSTED_FILE, "r", encoding="utf-8") as fichier:
            contenu = json.load(fichier)

        if not isinstance(contenu, list):
            raise ValueError("posted.json ne contient pas une liste.")

        historique = []
        ids_vus = set()

        for url in contenu:
            if not isinstance(url, str) or not url.strip():
                continue

            url_normalisee = normaliser_url(url)
            id_sujet = recuperer_id_sujet(url_normalisee)

            if not id_sujet:
                continue

            # Supprime aussi les éventuels anciens doublons
            # déjà présents dans posted.json.
            if id_sujet in ids_vus:
                continue

            ids_vus.add(id_sujet)
            historique.append(url_normalisee)

        return historique

    except FileNotFoundError:
        print("posted.json absent : création d'un nouvel historique.")
        return []

    except (json.JSONDecodeError, ValueError) as erreur:
        raise RuntimeError(
            f"Impossible de lire posted.json : {erreur}"
        )


def enregistrer_historique(historique):
    """
    Enregistre les sujets publiés sans doublon.
    """
    historique_nettoye = []
    ids_vus = set()

    for url in historique:
        url_normalisee = normaliser_url(url)
        id_sujet = recuperer_id_sujet(url_normalisee)

        if not id_sujet:
            continue

        if id_sujet in ids_vus:
            continue

        ids_vus.add(id_sujet)
        historique_nettoye.append(url_normalisee)

    with open(POSTED_FILE, "w", encoding="utf-8") as fichier:
        json.dump(
            historique_nettoye,
            fichier,
            ensure_ascii=False,
            indent=2
        )


# ==========================================================
# RÉCUPÉRATION DES SUJETS DE ROLL CALL
# ==========================================================

def recuperer_sujets():
    """
    Charge Roll Call et récupère les liens de sujets.

    Le bot reconnaît les sujets grâce à leur URL /tNUMERO,
    sans dépendre des classes HTML variables de Forumactif.
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

    # Recherche les liens correspondant aux sujets Forumactif :
    # /t2355-nom-du-sujet
    # t2355-nom-du-sujet
    # https://concretejungle.forumactif.com/t2355-nom-du-sujet
    liens = soup.find_all(
        "a",
        href=re.compile(
            r"^(?:https?://concretejungle\.forumactif\.com)?/?t\d+"
        )
    )

    sujets = []
    ids_vus = set()

    for lien in liens:
        titre = lien.get_text(" ", strip=True)
        href = lien.get("href", "").strip()

        if not titre or not href:
            continue

        url = normaliser_url(href)
        id_sujet = recuperer_id_sujet(url)

        if not id_sujet:
            continue

        if not url.startswith(f"{FORUM_URL}/t"):
            continue

        # Un même sujet peut être lié plusieurs fois dans le HTML.
        # Son identifiant numérique garantit qu'il ne sera gardé
        # qu'une seule fois.
        if id_sujet in ids_vus:
            continue

        ids_vus.add(id_sujet)

        sujets.append({
            "id": id_sujet,
            "title": titre,
            "link": url
        })

    print(f"Nombre de sujets uniques détectés : {len(sujets)}")

    for sujet in sujets:
        print(
            f"— Sujet #{sujet['id']} : "
            f"{sujet['title']} — {sujet['link']}"
        )

    if not sujets:
        titre_page = (
            soup.title.get_text(" ", strip=True)
            if soup.title
            else "inconnu"
        )

        print(f"Titre de la page reçue : {titre_page}")

        raise RuntimeError(
            "Aucun sujet n'a été détecté dans Roll Call. "
            "Forumactif a peut-être renvoyé une page différente."
        )

    return sujets


# ==========================================================
# PUBLICATION SUR DISCORD
# ==========================================================

def publier_sur_discord(sujet):
    """
    Envoie l'annonce et vérifie que Discord l'a acceptée.
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
        f"Réponse Discord pour le sujet "
        f"#{sujet['id']} : {reponse.status_code}"
    )

    if reponse.status_code not in (200, 204):
        raise RuntimeError(
            f"Discord a refusé le message du sujet "
            f"#{sujet['id']} : "
            f"{reponse.status_code} — {reponse.text[:500]}"
        )


# ==========================================================
# LANCEMENT
# ==========================================================

def main():
    historique = charger_historique()

    ids_deja_annonces = {
        recuperer_id_sujet(url)
        for url in historique
        if recuperer_id_sujet(url)
    }

    print(
        f"Nombre de sujets dans l'historique : "
        f"{len(ids_deja_annonces)}"
    )

    sujets = recuperer_sujets()

    nouveaux_sujets = [
        sujet
        for sujet in sujets
        if sujet["id"] not in ids_deja_annonces
    ]

    print(
        f"Nombre de nouveaux sujets à annoncer : "
        f"{len(nouveaux_sujets)}"
    )

    if not nouveaux_sujets:
        print("Aucun nouveau sujet à publier.")
        return

    # Publication du plus ancien au plus récent.
    for sujet in reversed(nouveaux_sujets):
        print(
            f"Publication du sujet #{sujet['id']} : "
            f"{sujet['title']}"
        )

        publier_sur_discord(sujet)

        # Le sujet est mémorisé uniquement après confirmation
        # de sa publication par Discord.
        historique.append(sujet["link"])
        ids_deja_annonces.add(sujet["id"])

        enregistrer_historique(historique)

        print(
            f"Sujet #{sujet['id']} publié et "
            f"ajouté à l'historique."
        )

    print("Toutes les nouvelles annonces ont été publiées.")


if __name__ == "__main__":
    try:
        main()

    except Exception as erreur:
        print(f"ERREUR DU BOT : {erreur}", file=sys.stderr)
        sys.exit(1)
