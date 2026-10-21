"""Deterministic catalog search vocabulary shared by SQL and domain adapters."""
from dataclasses import dataclass

from sqlalchemy import and_, or_, select

from app.db.models import ProductORM, ProductVariantORM


def _aliases(groups: dict[str, str]) -> dict[str, str]:
    return {word: key for key, words in groups.items() for word in words.split()}


PET_ALIASES = _aliases({
    'cat': 'кошка кошки кошек кошке кошку кот коты котов коту кота котенок котенка котята котят cat cats',
    'dog': 'собака собаки собак собаке собаку щенок щенка щенки щенков пес псы пса dog dogs',
    'bird': 'птица птицы птиц птице птичка птички попугай попугаи попугаев bird birds',
    'small_pet': 'грызун грызуны грызунов хомяк хомяки хомяков кролик кролики кроликов шиншилла шиншиллы',
    'fish': 'рыба рыбы рыб рыбка рыбки рыбок fish',
    'reptile': 'рептилия рептилии рептилий ящерица ящерицы змея змеи черепаха черепахи reptile reptiles',
    'amphibian': 'амфибия амфибии амфибий земноводные земноводных лягушка лягушки тритон тритоны',
    'invertebrate': 'беспозвоночные беспозвоночных паук пауки пауков улитка улитки насекомые насекомых',
})
KIND_ALIASES = _aliases({
    'food': 'корм корма кормов кормом корму food',
    'treats': 'лакомство лакомства лакомств лакомствами treats',
    'toys': 'игрушка игрушки игрушек игрушкой игрушками toys',
    'bowls': 'миска миски мисок поилка поилки поилок bowls',
    'litter': 'наполнитель наполнители наполнителя наполнителей litter',
    'habitats': 'домик домики домиков переноска переноски переносок habitats',
    'walking': 'прогулка прогулки прогулок поводок поводки поводков шлейка шлейки walking',
    'care': 'уход гигиена care',
    'aquatics': 'аквариум аквариумы аквариумов аквариумистика aquatics',
    'terrariums': 'террариум террариумы террариумов террариумистика terrariums',
})
CATEGORY_ALIASES = _aliases({'food': 'еда питание', 'accessory': 'аксессуар аксессуары аксессуаров'})
STOP_WORDS = frozenset({'для', 'и', 'в', 'на'})


@dataclass(frozen=True)
class SearchTerm:
    text: str
    pet_type: str | None = None
    product_kind: str | None = None
    category: str | None = None


def search_terms(query: str | None) -> tuple[SearchTerm, ...]:
    # Keep punctuation literal: SKU characters and SQL wildcard characters are never expanded.
    words = dict.fromkeys((query or '').strip().casefold().split())
    return tuple(SearchTerm(word, PET_ALIASES.get(word.replace('ё', 'е')),
                            KIND_ALIASES.get(word.replace('ё', 'е')),
                            CATEGORY_ALIASES.get(word.replace('ё', 'е')))
                 for word in words if word not in STOP_WORDS)


def product_search_criteria(query: str | None) -> list:
    criteria = []
    for term in search_terms(query):
        sku = select(ProductVariantORM.id).where(
            ProductVariantORM.product_id == ProductORM.id,
            ProductVariantORM.sku_normalized.contains(term.text, autoescape=True),
        ).correlate(ProductORM).exists()
        alternatives = [ProductORM.name_normalized.contains(term.text, autoescape=True),
                        ProductORM.brand_normalized.contains(term.text, autoescape=True), sku]
        if term.pet_type:
            alternatives.append(ProductORM.pet_type == term.pet_type)
        if term.product_kind:
            alternatives.append(ProductORM.product_kind == term.product_kind)
            if term.product_kind == 'food':
                alternatives.append(and_(ProductORM.product_kind.is_(None), ProductORM.category == 'food'))
        if term.category:
            alternatives.append(ProductORM.category == term.category)
        criteria.append(or_(*alternatives))
    return criteria


def product_matches_search(product, query: str | None) -> bool:
    return all(term.text in product.name.casefold()
               or term.text in product.brand.casefold()
               or any(term.text in variant.sku.casefold() for variant in product.variants)
               or (term.pet_type is not None and product.pet_type == term.pet_type)
               or (term.product_kind is not None and product.product_kind == term.product_kind)
               or (term.product_kind == 'food' and product.product_kind is None and product.category == 'food')
               or (term.category is not None and product.category == term.category)
               for term in search_terms(query))
