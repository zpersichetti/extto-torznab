from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Category:
    ext_id: int
    name: str
    newznab_id: int


@dataclass(frozen=True, slots=True)
class Subcategory:
    parent_id: int
    newznab_id: int
    name: str
    ext_id: int


# extto.com's top-level browse sections (cat=N) mapped to Newznab top-level IDs.
# Anime is deliberately absent: extto.com does have a dedicated Anime section, but
# in Newznab it is TV subcategory 5070, so it lives in SUBCATEGORIES below.
CATEGORIES = (
    Category(1, "Movies", 2000),
    Category(2, "TV", 5000),
    Category(3, "Audio", 3000),
    Category(4, "Console", 1000),
    Category(5, "PC", 4000),
    Category(6, "Books", 7000),
    Category(8, "Other", 8000),
)

# Full standard Newznab subcategory tree, advertised in caps so Prowlarr/RMAB and
# friends never drop this indexer for a subcategory query. Nearly all resolve to
# their parent's extto section; two reflect extto.com's actual layout:
#   - 3030 Audiobook -> extto Books (6): audiobooks are filed under Books, not Audio.
#   - 5070 Anime     -> extto Anime (7): extto has a dedicated Anime section.
SUBCATEGORIES = (
    # Console (extto cat 4)
    Subcategory(1000, 1010, "NDS", 4),
    Subcategory(1000, 1020, "PSP", 4),
    Subcategory(1000, 1030, "Wii", 4),
    Subcategory(1000, 1040, "XBox", 4),
    Subcategory(1000, 1050, "XBox 360", 4),
    Subcategory(1000, 1060, "Wiiware", 4),
    Subcategory(1000, 1070, "XBox 360 DLC", 4),
    Subcategory(1000, 1080, "PS3", 4),
    Subcategory(1000, 1090, "Other", 4),
    Subcategory(1000, 1110, "3DS", 4),
    Subcategory(1000, 1120, "PS Vita", 4),
    Subcategory(1000, 1130, "WiiU", 4),
    Subcategory(1000, 1140, "XBox One", 4),
    Subcategory(1000, 1180, "PS4", 4),
    # Movies (extto cat 1)
    Subcategory(2000, 2010, "Foreign", 1),
    Subcategory(2000, 2020, "Other", 1),
    Subcategory(2000, 2030, "SD", 1),
    Subcategory(2000, 2040, "HD", 1),
    Subcategory(2000, 2045, "UHD", 1),
    Subcategory(2000, 2050, "BluRay", 1),
    Subcategory(2000, 2060, "3D", 1),
    Subcategory(2000, 2070, "DVD", 1),
    Subcategory(2000, 2080, "WEB-DL", 1),
    Subcategory(2000, 2090, "x265", 1),
    # Audio (extto cat 3)
    Subcategory(3000, 3010, "MP3", 3),
    Subcategory(3000, 3020, "Video", 3),
    Subcategory(3000, 3030, "Audiobook", 6),  # audiobooks live under Books
    Subcategory(3000, 3040, "Lossless", 3),
    Subcategory(3000, 3050, "Other", 3),
    Subcategory(3000, 3060, "Foreign", 3),
    # PC (extto cat 5)
    Subcategory(4000, 4010, "0day", 5),
    Subcategory(4000, 4020, "ISO", 5),
    Subcategory(4000, 4030, "Mac", 5),
    Subcategory(4000, 4040, "Mobile-Other", 5),
    Subcategory(4000, 4050, "Games", 5),
    Subcategory(4000, 4060, "Mobile-iOS", 5),
    Subcategory(4000, 4070, "Mobile-Android", 5),
    # TV (extto cat 2)
    Subcategory(5000, 5010, "WEB-DL", 2),
    Subcategory(5000, 5020, "Foreign", 2),
    Subcategory(5000, 5030, "SD", 2),
    Subcategory(5000, 5040, "HD", 2),
    Subcategory(5000, 5045, "UHD", 2),
    Subcategory(5000, 5050, "Other", 2),
    Subcategory(5000, 5060, "Sport", 2),
    Subcategory(5000, 5070, "Anime", 7),  # extto has a dedicated Anime section
    Subcategory(5000, 5080, "Documentary", 2),
    Subcategory(5000, 5090, "x265", 2),
    # Books (extto cat 6)
    Subcategory(7000, 7010, "Mags", 6),
    Subcategory(7000, 7020, "EBook", 6),
    Subcategory(7000, 7030, "Comics", 6),
    Subcategory(7000, 7040, "Technical", 6),
    Subcategory(7000, 7050, "Other", 6),
    Subcategory(7000, 7060, "Foreign", 6),
    # Other (extto cat 8)
    Subcategory(8000, 8010, "Misc", 8),
    Subcategory(8000, 8020, "Hashed", 8),
)

# Page-breadcrumb name -> Newznab ID, used to tag a parsed torrent's category.
NAME_TO_NEWZNAB = {
    "movies": 2000,
    "movie": 2000,
    "tv": 5000,
    "tv series": 5000,
    "music": 3000,
    "audio": 3000,
    "games": 1000,
    "console": 1000,
    "apps": 4000,
    "applications": 4000,
    "pc": 4000,
    "books": 7000,
    "anime": 5070,
    "other": 8000,
}


def ext_category_for(newznab_id: int | None) -> int | None:
    """Map a Newznab category id to the extto.com browse section (cat=N).

    Subcategories resolve to their parent section by default, with two layout
    exceptions: audiobook -> Books, anime -> the dedicated Anime section.
    """
    if newznab_id is None:
        return None
    for category in CATEGORIES:
        if category.newznab_id == newznab_id:
            return category.ext_id
    for subcategory in SUBCATEGORIES:
        if subcategory.newznab_id == newznab_id:
            return subcategory.ext_id
    parent = newznab_id // 1000 * 1000
    for category in CATEGORIES:
        if category.newznab_id == parent:
            return category.ext_id
    return None
