"""Demonstration data used by the in-memory repository."""
from .models import Accessory, Food, Product, ProductVariant


def demo_products() -> list[Product]:
    """Return 20 new demo products on every application start."""
    products: list[Product] = []
    for i in range(1, 21):
        pet = 'cat' if i % 2 else 'dog'
        animal = 'кошек' if pet == 'cat' else 'собак'
        is_food = i <= 10
        variants = [
            ProductVariant(
                i * 10,
                f'DEMO-{i}-S',
                '400 г' if is_food else 'S',
                str(1000 + i * 200),
                5 if i % 4 else 0,
            )
        ]
        if i <= 5:
            variants.append(ProductVariant(i * 10 + 1, f'DEMO-{i}-L', '2 кг', '6000', 3))
        if i == 1:
            variants[0].change_price('1000')
            variants[0].set_stock(0)
        args = (
            i,
            f'{"Корм" if is_food else "Ошейник"} для {animal} №{i}',
            pet,
            'DemoPet' if is_food else 'DemoZoo',
            variants,
        )
        products.append(
            Food(*args, composition='курица, рис')
            if is_food
            else Accessory(*args, material='нейлон')
        )
    return products
