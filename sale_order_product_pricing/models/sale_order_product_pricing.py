"""Retired legacy Product Pricing model.

Product Pricing used to duplicate sale order lines in a writable
``sale.order.product.pricing`` model.  It is intentionally no longer imported:
``sale.order.line`` is the only pricing authority.  This module remains as a
source-level marker for migration tooling and downstream maintainers; do not
re-enable the old model or create a second editable line collection.
"""
