"""Catalog-specific exceptions independent from HTTP."""


class CatalogError(Exception):
    """Base error for catalog business rules."""


class ProductNotFoundError(CatalogError):
    pass


class VariantNotFoundError(CatalogError):
    pass


class DuplicateSKUError(CatalogError):
    pass


class InvalidCatalogDataError(CatalogError):
    pass
