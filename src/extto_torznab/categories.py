from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Category:
    ext_id: int
    name: str
    newznab_id: int


# Verified against extto.com's cat=1..8 navigation/browse sections on 2026-08-28.
CATEGORIES = (
    Category(1, "Movies", 2000),
    Category(2, "TV", 5000),
    Category(3, "Audio", 3000),
    Category(4, "Console", 1000),
    Category(5, "PC", 4000),
    Category(6, "Books", 7000),
    Category(7, "Anime", 5070),
    Category(8, "Other", 8000),
)

EXT_TO_NEWZNAB = {category.ext_id: category.newznab_id for category in CATEGORIES}
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


def ext_category_for(newznab_category: int | None) -> int | None:
    if newznab_category is None:
        return None
    exact = next(
        (category.ext_id for category in CATEGORIES if category.newznab_id == newznab_category),
        None,
    )
    if exact is not None:
        return exact
    parent = newznab_category // 1000 * 1000
    return next(
        (category.ext_id for category in CATEGORIES if category.newznab_id == parent),
        None,
    )
