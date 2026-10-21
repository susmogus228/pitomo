"""Small OOP demonstration without starting the HTTP server."""
from app.catalog.repository import InMemoryProductRepository
from app.catalog.seed import demo_products


if __name__ == '__main__':
    repository = InMemoryProductRepository(demo_products())
    for product in (repository.get(1), repository.get(11)):
        print(type(product).__name__, '→', product.get_description())

    variant = repository.get(1).variants[0]
    variant.change_price('1250.50')
    variant.set_stock(2)
    print('Новая цена:', variant.price, variant.currency, '| Остаток:', variant.stock)

    try:
        variant.set_stock(-1)
    except ValueError as error:
        print('Некорректное изменение отклонено:', error)
