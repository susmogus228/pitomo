"""Versioned demo catalog metadata; these are not real manufacturer offers."""
from dataclasses import dataclass


@dataclass(frozen=True)
class DemoProduct:
    pet_type: str
    number: int
    name: str
    product_kind: str
    label: str
    asset: str

    @property
    def sku(self) -> str:
        return f'PITOMO-DEMO-{self.pet_type.upper()}-{self.number:02d}'

    @property
    def category(self) -> str:
        return 'food' if self.product_kind in {'food', 'treats'} else 'accessory'

    @property
    def full_name(self) -> str:
        return self.name + ' · Демо'

    @property
    def image_url(self) -> str:
        return f'/media/products/v2/{self.asset}.webp'

    @property
    def detail(self) -> str:
        return ('Демонстрационный товар. Совместимость и ' +
                ('состав' if self.category == 'food' else 'характеристики') +
                ' требуют проверки перед реальной продажей')


DEMO_PRODUCTS = (
    DemoProduct('cat', 1, 'Корм для кошек', 'food', '500 г', 'cat-food'),
    DemoProduct('cat', 2, 'Игрушка с перьями для кошек', 'toys', '1 шт.', 'cat-feather-toy'),
    DemoProduct('cat', 3, 'Керамическая миска для кошек', 'bowls', '1 шт.', 'cat-ceramic-bowl'),
    DemoProduct('cat', 4, 'Лакомство для кошек', 'treats', '60 г', 'cat-treats'),
    DemoProduct('cat', 5, 'Древесный наполнитель для кошачьего туалета', 'litter', '5 л', 'cat-wood-litter'),
    DemoProduct('cat', 6, 'Переноска для кошек', 'habitats', '48 × 32 × 31 см', 'cat-carrier'),
    DemoProduct('dog', 1, 'Корм для собак', 'food', '500 г', 'dog-food'),
    DemoProduct('dog', 2, 'Мяч для прогулок с собакой', 'toys', '1 шт.', 'dog-ball'),
    DemoProduct('dog', 3, 'Миска для воды для собак', 'bowls', '1 шт.', 'dog-water-bowl'),
    DemoProduct('dog', 4, 'Поводок для собак', 'walking', '2 м', 'dog-leash'),
    DemoProduct('dog', 5, 'Щётка для шерсти собак', 'care', '1 шт.', 'dog-brush'),
    DemoProduct('dog', 6, 'Лакомство для собак', 'treats', '100 г', 'dog-treats'),
    DemoProduct('bird', 1, 'Зерновая смесь для волнистых попугаев', 'food', '500 г', 'budgie-seed'),
    DemoProduct('bird', 2, 'Качели для небольших попугаев', 'toys', '1 шт.', 'bird-swing'),
    DemoProduct('bird', 3, 'Гнездовой домик для волнистых попугаев', 'habitats', '1 шт.', 'budgie-nest-box'),
    DemoProduct('bird', 4, 'Поилка для клетки с попугаями', 'bowls', '100 мл', 'bird-drinker'),
    DemoProduct('bird', 5, 'Купалка для небольших попугаев', 'care', '14 × 12 см', 'bird-bath'),
    DemoProduct('bird', 6, 'Просо в колосьях для попугаев', 'treats', '100 г', 'bird-millet'),
    DemoProduct('small_pet', 1, 'Сено для кроликов', 'food', '500 г', 'rabbit-hay'),
    DemoProduct('small_pet', 2, 'Туннель для хомяков', 'toys', '1 шт.', 'hamster-tunnel'),
    DemoProduct('small_pet', 3, 'Деревянный домик для хомяков', 'habitats', '1 шт.', 'hamster-house'),
    DemoProduct('small_pet', 4, 'Подвесная поилка для грызунов', 'bowls', '250 мл', 'rodent-drinker'),
    DemoProduct('small_pet', 5, 'Бумажная подстилка для хомяков', 'litter', '10 л', 'hamster-paper-bedding'),
    DemoProduct('small_pet', 6, 'Сушёные листья подорожника для кроликов', 'treats', '50 г', 'rabbit-plantain'),
    DemoProduct('fish', 1, 'Хлопья для декоративных рыб', 'food', '500 г', 'fish-flakes'),
    DemoProduct('fish', 2, 'Керамический аквариумный декор', 'aquatics', '1 шт.', 'aquarium-cave'),
    DemoProduct('fish', 3, 'Стеклянный аквариум', 'aquatics', '1 шт.', 'glass-aquarium'),
    DemoProduct('fish', 4, 'Губчатый фильтр для аквариума', 'aquatics', '1 шт.', 'aquarium-sponge-filter'),
    DemoProduct('fish', 5, 'Сачок для аквариума', 'aquatics', '10 см', 'aquarium-net'),
    DemoProduct('fish', 6, 'Тест-полоски для аквариумной воды', 'care', '25 шт.', 'aquarium-water-tests'),
    DemoProduct('reptile', 1, 'Гранулы для водных черепах', 'food', '500 г', 'aquatic-turtle-food'),
    DemoProduct('reptile', 2, 'Укрытие для рептилий', 'terrariums', '1 шт.', 'reptile-hide'),
    DemoProduct('reptile', 3, 'Субстрат из коры для террариума', 'terrariums', '1 шт.', 'reptile-bark-substrate'),
    DemoProduct('reptile', 4, 'Стеклянный террариум', 'terrariums', '45 × 45 × 45 см', 'glass-terrarium'),
    DemoProduct('reptile', 5, 'Термометр с выносным датчиком для террариума', 'terrariums', '1 шт.', 'terrarium-probe-thermometer'),
    DemoProduct('reptile', 6, 'Неглубокая поилка для террариума', 'bowls', '12 × 9 см', 'reptile-shallow-bowl'),
    DemoProduct('amphibian', 1, 'Тонущие гранулы для аксолотлей', 'food', '500 г', 'axolotl-pellets'),
    DemoProduct('amphibian', 2, 'Неглубокая поилка для террариума амфибий', 'bowls', '1 шт.', 'amphibian-water-dish'),
    DemoProduct('amphibian', 3, 'Укрытие для террариума амфибий', 'terrariums', '1 шт.', 'amphibian-hide'),
    DemoProduct('amphibian', 4, 'Гигрометр для террариума', 'terrariums', '1 шт.', 'amphibian-hygrometer'),
    DemoProduct('amphibian', 5, 'Ручной распылитель для террариума', 'care', '500 мл', 'terrarium-mister'),
    DemoProduct('amphibian', 6, 'Пологая платформа для палюдариума', 'terrariums', '20 × 14 см', 'paludarium-ramp'),
    DemoProduct('invertebrate', 1, 'Кормовая смесь для изопод', 'food', '500 г', 'isopod-food'),
    DemoProduct('invertebrate', 2, 'Кокосовый субстрат для террариума', 'terrariums', '1 шт.', 'coco-substrate'),
    DemoProduct('invertebrate', 3, 'Контейнер для краткого наблюдения', 'terrariums', '1 шт.', 'observation-container'),
    DemoProduct('invertebrate', 4, 'Мини-гигрометр для террариума', 'terrariums', '1 шт.', 'invertebrate-hygrometer'),
    DemoProduct('invertebrate', 5, 'Пробковая кора для террариума', 'terrariums', '20 × 10 см', 'cork-bark'),
    DemoProduct('invertebrate', 6, 'Кормовая площадка для изопод', 'bowls', '6 см', 'isopod-feeding-dish'),
)
