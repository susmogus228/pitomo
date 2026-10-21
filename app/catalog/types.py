"""Shared catalog vocabulary; category remains backwards compatible."""
from typing import Literal

PetType = Literal['cat', 'dog', 'bird', 'small_pet', 'fish', 'reptile', 'amphibian', 'invertebrate']
PET_TYPES = ('cat', 'dog', 'bird', 'small_pet', 'fish', 'reptile', 'amphibian', 'invertebrate')

ProductKind = Literal['food', 'treats', 'toys', 'bowls', 'litter', 'habitats', 'walking', 'care', 'aquatics', 'terrariums']
PRODUCT_KINDS = (
    ('food', 'Корма'), ('treats', 'Лакомства'), ('toys', 'Игрушки'),
    ('bowls', 'Миски и поилки'), ('litter', 'Наполнители'),
    ('habitats', 'Домики и переноски'), ('walking', 'Прогулка'),
    ('care', 'Уход'), ('aquatics', 'Аквариумистика'), ('terrariums', 'Террариумы'),
)
PRODUCT_KIND_IDS = frozenset(kind for kind, _ in PRODUCT_KINDS)
