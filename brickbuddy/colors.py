"""Couleurs LEGO officielles et noms français."""
from .flask_app import app

# Couleurs LEGO officielles (noms Rebrickable -> hexadecimal RGB).
# Source : https://rebrickable.com/colors/ (273 couleurs, capture du 30/10/2026).
LEGO_COLOR_HEX = {
    "Black": "#05131D",
    "White": "#FFFFFF",
    "Red": "#C91A09",
    "Blue": "#0055BF",
    "Green": "#237841",
    "Yellow": "#F2CD37",
    "Orange": "#FE8A18",
    "Dark Orange": "#A95500",
    "Medium Orange": "#FFA70B",
    "Bright Light Orange": "#F8BB3D",
    "Light Orange": "#F9BA61",
    "Very Light Orange": "#F3CF9B",
    "Dark Red": "#720E0F",
    "Brown": "#583927",
    "Reddish Brown": "#582A12",
    "Dark Brown": "#352100",
    "Light Brown": "#7C503A",
    "Medium Brown": "#755945",
    "Tan": "#E4CD9E",
    "Dark Tan": "#958A73",
    "Light Tan": "#F3C988",
    "Nougat": "#D09168",
    "Light Nougat": "#F6D7B3",
    "Medium Nougat": "#AA7D55",
    "Dark Nougat": "#AD6140",
    "Pink": "#FC97AC",
    "Light Pink": "#FECCCF",
    "Bright Pink": "#E4ADC8",
    "Dark Pink": "#C870A0",
    "Medium Dark Pink": "#F785B1",
    "Light Salmon": "#FEBABD",
    "Salmon": "#F2705E",
    "Coral": "#FF698F",
    "Bright Reddish Orange": "#EE5434",
    "Reddish Orange": "#CA4C0B",
    "Sand Red": "#D67572",
    "Earth Orange": "#FA9C1C",
    "Rust": "#B31004",
    "Magenta": "#923978",
    "Purple": "#81007B",
    "Dark Purple": "#3F3691",
    "Light Purple": "#CD6298",
    "Medium Violet": "#9391E4",
    "Violet": "#4354A3",
    "Dark Blue-Violet": "#2032B0",
    "Medium Bluish Violet": "#6874CA",
    "Lavender": "#E1D5ED",
    "Medium Lavender": "#AC78BA",
    "Light Lilac": "#9195CA",
    "Reddish Lilac": "#8E5597",
    "Sand Purple": "#845E84",
    "Lime": "#BBE90B",
    "Medium Lime": "#C7D23C",
    "Light Lime": "#D9E4A7",
    "Yellowish Green": "#DFEEA5",
    "Olive Green": "#9B9A5A",
    "Bright Green": "#4B9F4A",
    "Medium Green": "#73DCA1",
    "Light Green": "#C2DAB8",
    "Sand Green": "#A0BCAC",
    "Dark Green": "#184632",
    "Bright Light Yellow": "#FFF03A",
    "Light Yellow": "#FBE696",
    "Dark Turquoise": "#008F9B",
    "Light Turquoise": "#55A5AF",
    "Aqua": "#B3D7D1",
    "Light Aqua": "#ADC3C0",
    "Sky Blue": "#7DBFDD",
    "Medium Azure": "#36AEBF",
    "Dark Azure": "#078BC9",
    "Maersk Blue": "#3592C3",
    "Pastel Blue": "#5AC4DA",
    "Light Blue": "#B4D2E3",
    "Bright Light Blue": "#9FC3E9",
    "Medium Blue": "#5A93DB",
    "Dark Blue": "#0A3463",
    "Royal Blue": "#4C61DB",
    "Sand Blue": "#6074A1",
    "Light Bluish Gray": "#A0A5A9",
    "Dark Bluish Gray": "#6C6E68",
    "Light Gray": "#9BA19D",
    "Dark Gray": "#6D6E5C",
    "Very Light Bluish Gray": "#E6E3E0",
    "Very Light Gray": "#E6E3DA",
    "Milky White": "#FFFFFF",
    "Trans-Clear": "#FCFCFC",
    "Trans-Black": "#635F52",
    "Trans-Brown": "#635F52",
    "Trans-Black IR Lens": "#635F52",
    "Trans-Red": "#C91A09",
    "Trans-Yellow": "#F5CD2F",
    "Trans-Neon Yellow": "#DAB000",
    "Trans-Neon Green": "#F8F184",
    "Trans-Neon Orange": "#FF800D",
    "Trans-Neon Red": "#FF0040",
    "Trans-Orange": "#F08F1C",
    "Trans-Flame Yellowish Orange": "#FCB76D",
    "Trans-Fire Yellow": "#FBE890",
    "Trans-Dark Blue": "#0020A0",
    "Trans-Medium Blue": "#CFE2F7",
    "Trans-Light Blue": "#AEEFEC",
    "Trans-Very Lt Blue": "#C1DFF0",
    "Trans-Light Royal Blue": "#B4D4F7",
    "Trans-Green": "#84B68D",
    "Trans-Bright Green": "#D9E4A7",
    "Trans-Light Bright Green": "#C9E788",
    "Trans-Light Green": "#94E5AB",
    "Trans-Purple": "#A5A5CB",
    "Trans-Medium Purple": "#8D73B3",
    "Trans-Light Purple": "#96709F",
    "Trans-Dark Pink": "#DF6695",
    "Trans-Pink": "#E4ADC8",
    "Glitter Trans-Clear": "#FFFFFF",
    "Glitter Trans-Orange": "#F08F1C",
    "Glitter Trans-Bright Green": "#D9E4A7",
    "Glitter Trans-Neon Green": "#C0F500",
    "Glitter Trans-Light Blue": "#68BCC5",
    "Glitter Trans-Purple": "#A5A5CB",
    "Glitter Trans-Medium Purple": "#8D73B3",
    "Glitter Trans-Pink": "#E4ADC8",
    "Glitter Trans-Green": "#84B68D",
    "Glitter Trans-Dark Pink": "#DF6695",
    "Opal Trans-Clear": "#FCFCFC",
    "Opal Trans-Brown": "#583927",
    "Opal Trans-Yellow": "#F5CD2F",
    "Opal Trans-Bright Green": "#84B68D",
    "Opal Trans-Light Blue": "#68BCC5",
    "Opal Trans-Dark Blue": "#0020A0",
    "Opal Trans-Dark Pink": "#CE1D9B",
    "Opal Trans-Purple": "#8320B7",
    "Glow In Dark Trans": "#BDC6AD",
    "Flat Silver": "#898788",
    "Flat Dark Gold": "#B48455",
    "Metallic Silver": "#A5A9B4",
    "Metallic Green": "#899B5F",
    "Metallic Gold": "#DBAC34",
    "Metallic Copper": "#764D3B",
    "Metal": "#A5ADB4",
    "Chrome Silver": "#E0E0E0",
    "Chrome Gold": "#BBA53D",
    "Chrome Antique Brass": "#645A4C",
    "Chrome Blue": "#6C96BF",
    "Chrome Green": "#3CB371",
    "Chrome Pink": "#AA4D8E",
    "Chrome Black": "#1B2A34",
    "Chrome Red": "#CE3021",
    "Copper": "#AE7A59",
    "Reddish Gold": "#AC8247",
    "Speckle Black-Copper": "#05131D",
    "Speckle Black-Silver": "#05131D",
    "Speckle Black-Gold": "#05131D",
    "Speckle DBGray-Silver": "#6C6E68",
    "Pearl Light Gray": "#9CA3A8",
    "Pearl Dark Gray": "#575857",
    "Pearl Very Light Gray": "#ABADAC",
    "Pearl White": "#F2F3F2",
    "Pearl Gold": "#AA7F2E",
    "Pearl Light Gold": "#DCBC81",
    "Pearl Copper": "#B46A00",
    "Pearl Brown": "#57392C",
    "Pearl Black": "#0A1327",
    "Pearl Blue": "#0059A3",
    "Pearl Green": "#008E3C",
    "Pearl Red": "#D60026",
    "Pearl Lime": "#6A7944",
    "Pearl Sand Blue": "#7988A1",
    "Pearl Titanium": "#3E3C39",
    "Glow In Dark Opaque": "#D4D5C9",
    "Glow in Dark White": "#D9D9D9",
}



# Couleurs sans brique reelle : pas de degrade possible sur les en-tetes.
COLORS_WITHOUT_HEX = {"", "Figurine", "[No Color/Any Color]"}



# Couleurs saisies à la main en français : elles ramènent le nom officiel Rebrickable.
FRENCH_COLOR_ALIASES = {
    "noir": "Black",
    "blanc": "White",
    "rouge": "Red",
    "bleu": "Blue",
    "vert": "Green",
    "jaune": "Yellow",
    "orange": "Orange",
    "violet": "Purple",
    "brun": "Brown",
}



# Noms officiels avec leur casse : une saisie en lowercase (« tan ») retrouve « Tan ».
PALETTE_BY_LOWER = {name.casefold(): name for name in LEGO_COLOR_HEX}


def official_color_name(color_name):
    """Nom officiel Rebrickable d'une couleur, y compris saisie en français ou en lowercase."""
    lowered = (color_name or "").casefold()
    return FRENCH_COLOR_ALIASES.get(lowered) or PALETTE_BY_LOWER.get(lowered) or color_name


# Les couleurs se lisent en anglais, toujours : « Rouge » et « Red » sont la même
# couleur et portent le même titre, « Black » reste « Black ». Les noms saisis en
# français sont reconnus (FRENCH_COLOR_ALIASES) mais jamais affichés.
# Les teintes dérivées (« Dark Blue ») gardent leur nom officiel : pas de piège
# pour les pastilles de couleur, dont la classe vient du libellé.
def color_group_label(color_name):
    """Libellé affiché d'une couleur : son nom officiel anglais, pour toutes ses graphies."""
    return official_color_name(color_name) or ""


# Un mot français trouve la couleur officielle correspondante : la seule place où le
# français sert encore, l'affichage reste en anglais.
FRENCH_SEARCH_WORDS = {official: french for french, official in FRENCH_COLOR_ALIASES.items()}


def search_terms(color_name):
    """Les mots que la recherche compare pour une couleur : le libellé, la saisie brute, le mot français."""
    return (
        color_group_label(color_name),
        color_name or "",
        FRENCH_SEARCH_WORDS.get(official_color_name(color_name)) or "",
    )


def color_group_key(color_name):
    """Cle de regroupement : le nom officiel, sans casse. « rouge » et « Red » ont la même cle."""
    return (official_color_name(color_name) or "").casefold()


def color_options(color_names):
    """Une ligne de menu par couleur : valeur = nom officiel (le filtre), texte = libellé."""
    options = {}
    for color_name in color_names:
        options.setdefault(
            color_group_key(color_name),
            {"value": official_color_name(color_name) or "", "label": color_group_label(color_name)},
        )
    return sorted(options.values(), key=lambda option: option["label"].casefold())



@app.template_filter("lego_color_hex")
def lego_color_hex(color_name):
    if not color_name or color_name in COLORS_WITHOUT_HEX:
        return None
    return LEGO_COLOR_HEX.get(official_color_name(color_name))
