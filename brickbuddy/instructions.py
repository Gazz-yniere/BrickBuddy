"""Notices LEGO : recherche, enregistrement, lecture, suppression."""
from . import auth
from . import config
from . import db
from . import images
from .flask_app import app
from flask import abort, render_template, url_for
from html.parser import HTMLParser
from pathlib import Path
import http.client
import os
import re
import secrets
import tempfile
import urllib.error
import urllib.parse
import urllib.request

def instruction_directory():
    return db.DATABASE_PATH.parent / "instructions"



def instruction_set(set_id):
    with db.database() as connection:
        item = connection.execute(
            "SELECT id, set_num, title FROM sets WHERE id = ?", (set_id,)
        ).fetchone()
    if item is None:
        abort(404)
    return item



def check_instruction_csrf():
    if not auth.form_csrf_ok():
        abort(400, description="Formulaire expiré. Rechargez la page.")



def lego_instruction_url(url):
    try:
        parsed = urllib.parse.urlsplit(url)
        return (
            parsed.scheme == "https"
            and parsed.hostname == "www.lego.com"
            and parsed.port in (None, 443)
            and not parsed.username
            and not parsed.password
            and parsed.path.startswith("/cdn/product-assets/product.bi.")
            and parsed.path.lower().endswith(".pdf")
            and not parsed.query
            and not parsed.fragment
        )
    except ValueError:
        return False



def lego_instruction_image_url(url):
    try:
        parsed = urllib.parse.urlsplit(url)
        return (
            parsed.scheme == "https"
            and parsed.hostname == "www.lego.com"
            and parsed.port in (None, 443)
            and not parsed.username
            and not parsed.password
            and parsed.path.startswith("/cdn/product-assets/product.bi.core.img/")
            and parsed.path.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
        )
    except ValueError:
        return False



def instruction_image_url(url):
    parsed = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))



class LegoInstructionParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.titles = {}
        self.heading_id = None
        self.heading_text = []
        self.card_image = ""
        self.card_heading_id = None

    def handle_starttag(self, tag, attrs):
        attrs = {name: value or "" for name, value in attrs}
        if tag == "li":
            self.card_image = ""
            self.card_heading_id = None
        elif tag in ("source", "img"):
            for candidate in (attrs.get("srcset", ""), attrs.get("srcSet", ""), attrs.get("src", "")):
                for part in candidate.split(","):
                    url = urllib.parse.urljoin(
                        "https://www.lego.com", part.strip().split(" ")[0]
                    )
                    if lego_instruction_image_url(url):
                        self.card_image = instruction_image_url(url)
                        break
                if self.card_image:
                    break
        if tag == "h3" and attrs.get("id") is not None:
            self.heading_id = attrs["id"]
            self.heading_text = []
            self.card_heading_id = attrs["id"]
        if tag != "a":
            return
        url = urllib.parse.urljoin("https://www.lego.com", attrs.get("href", ""))
        if lego_instruction_url(url) and not any(link["url"] == url for link in self.links):
            self.links.append({
                "url": url,
                "heading_id": attrs.get("aria-describedby", "") or self.card_heading_id or "",
                "image": self.card_image,
            })

    def handle_data(self, data):
        if self.heading_id is not None:
            self.heading_text.append(data)

    def handle_endtag(self, tag):
        if tag == "h3" and self.heading_id is not None:
            self.titles[self.heading_id] = " ".join("".join(self.heading_text).split())
            self.heading_id = None

    def instructions(self):
        return [
            {
                "url": link["url"],
                "title": self.titles.get(link["heading_id"], "")[:255],
                "image": link["image"],
                "position": index,
            }
            for index, link in enumerate(self.links)
        ]



class LegoPageRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urllib.parse.urlsplit(newurl)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "www.lego.com"
            or parsed.port not in (None, 443)
            or parsed.username
            or parsed.password
        ):
            raise ValueError("Redirection LEGO vers un domaine non autorisé.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)



class LegoPdfRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not lego_instruction_url(newurl):
            raise ValueError("Redirection de notice vers une adresse non autorisée.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)



def find_lego_instructions(set_num):
    number = set_num.split("-", 1)[0]
    if not re.fullmatch(r"[0-9]{1,12}", number):
        raise ValueError("Cette référence ne permet pas de rechercher une notice LEGO automatiquement.")
    url = f"https://www.lego.com/fr-fr/service/building-instructions/{number}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.build_opener(LegoPageRedirectHandler()).open(req, timeout=20) as response:
            content = response.read(config.MAX_INSTRUCTION_PAGE_BYTES + 1)
        if len(content) > config.MAX_INSTRUCTION_PAGE_BYTES:
            raise ValueError("La réponse LEGO dépasse la taille autorisée.")
        parser = LegoInstructionParser()
        parser.feed(content.decode("utf-8"))
        return parser.instructions()
    except (urllib.error.URLError, TimeoutError, UnicodeError, ValueError, http.client.HTTPException) as error:
        app.logger.warning("Recherche des notices LEGO impossible : %s", error)
        raise RuntimeError("Impossible de rechercher les notices LEGO. Réessaie plus tard.") from error



def instruction_order(manual):
    """Ordre du carrousel : position annoncee par LEGO, puis nom de fichier naturel."""
    natural_name = tuple(
        (1, int(part)) if part.isdecimal() else (0, part.casefold())
        for part in re.split(r"(\d+)", manual["filename"])
    )
    return (
        manual["source_position"] is None,
        manual["source_position"] if manual["source_position"] is not None else 0,
        natural_name if manual["source_position"] is None else (),
        manual["insertion_order"],
    )



def saved_instructions(set_num):
    """Notices enregistrees pour une reference, dans l'ordre du carrousel, taille du PDF comprise.

    La taille sert au navigateur pour precharger les livres voisins sans
    telecharger un PDF de plusieurs dizaines de Mo.
    """
    with db.database() as connection:
        rows = connection.execute(
            """SELECT id, filename, display_title, source_url, source_position, rowid AS insertion_order
               FROM set_instructions WHERE set_num = ?""",
            (set_num,),
        ).fetchall()
    instruction_files = instruction_directory()
    ordered = sorted(rows, key=instruction_order)
    uploads = 0
    numbered = []
    for manual in ordered:
        # Le numero de livre est celui annonce par LEGO, telecharge ou non :
        # une proposition qui devient une notice enregistree garde son numero,
        # et deux notices n'affichent jamais le meme. Les PDF ajoutes a la main
        # sont comptes a part, ils ne correspondent a aucun livre LEGO.
        if manual["source_position"] is None:
            uploads += 1
            label = f"Ajout {uploads}"
        else:
            label = f"Livre {manual['source_position'] + 1}"
        path = instruction_files / f"{manual['id']}.pdf"
        numbered.append(dict(
            manual,
            size=path.stat().st_size if path.is_file() else 0,
            book_label=label,
        ))
    return numbered



def instruction_card_payload(item, manuals, notice_id):
    """Reponse d'un telechargement AJAX : la tuile deja rendue, pour que le
    navigateur remplace la proposition par la notice enregistree sans recharger
    la page, et affiche le lecteur immediatement."""
    index = next((position for position, manual in enumerate(manuals) if manual["id"] == notice_id), 0)
    return {
        "saved": True,
        "notice_id": notice_id,
        "notice_url": url_for("set_instructions", set_id=item["id"], notice=notice_id),
        "pdf_url": url_for("instruction_pdf", set_id=item["id"], notice_id=notice_id),
        "html": render_template(
            "_instruction_card.html", set=item, manual=manuals[index], current=True,
        ),
    }



def save_instruction(
    set_num, filename, stream, source_url="", expected_length=None,
    display_title="", source_position=None,
):
    directory = instruction_directory()
    directory.mkdir(parents=True, exist_ok=True)
    notice_id = secrets.token_hex(16)
    destination = directory / f"{notice_id}.pdf"
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(dir=directory, suffix=".tmp", delete=False) as temp:
            temporary_path = Path(temp.name)
            header = stream.read(5)
            if header != b"%PDF-":
                raise ValueError("Le fichier ne semble pas être un PDF valide.")
            temp.write(header)
            size = len(header)
            while chunk := stream.read(1024 * 1024):
                size += len(chunk)
                if size > config.MAX_INSTRUCTION_BYTES:
                    raise ValueError("La notice dépasse la limite de 200 Mo.")
                temp.write(chunk)
            if expected_length is not None and size != expected_length:
                raise ValueError("Le téléchargement de la notice est incomplet.")
        os.replace(temporary_path, destination)
        try:
            with db.database() as connection:
                connection.execute(
                    """INSERT INTO set_instructions
                       (id, set_num, filename, source_url, display_title, source_position)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (notice_id, set_num, filename, source_url, display_title, source_position),
                )
        except Exception:
            destination.unlink(missing_ok=True)
            raise
    finally:
        if temporary_path:
            temporary_path.unlink(missing_ok=True)
    return notice_id



def proposal_tile_html(item, manual):
    """Tuile de proposition d'un livre LEGO dont la notice vient d'etre retiree.

    Le numero du livre etant porte par la notice enregistree, la proposition
    retrouve exactement la meme place et le meme numero dans le carrousel.
    """
    url = manual["source_url"]
    if manual["source_position"] is None or not lego_instruction_url(url):
        return ""
    return render_template(
        "_instruction_download_tile.html",
        set=item,
        instruction={
            "url": url,
            "title": manual["display_title"] or manual["filename"],
            "image": images.instruction_cover_url(url),
            "position": manual["source_position"],
        },
    )
