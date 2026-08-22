# -*- coding: utf-8 -*-

from odoo.tests import TransactionCase


class TestSaleOrderGlobalFactorAuthority(TransactionCase):
    """Regression tests for the quotation-wide global factor invariant.

    ``sale.order.global_factor`` is the single authoritative source for the
    ``factor`` value of every product line.  ``factor`` is a stored, precomputed
    related field (``order_id.global_factor``), so:

    * lines created in any way inherit the current header factor at creation,
    * writing the header factor updates all existing lines server-side,
    * the old onchange-based synchronization is gone; these tests force real
      database persistence by flushing and invalidating the cache before every
      assertion on ``factor``.

    ``line_factor`` stays a separate per-line adjustment and keeps driving
    ``estimate_unit_price`` exactly as before.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({
            'name': 'Global Factor Customer',
        })
        cls.product_a = cls.env['product.product'].create({
            'name': 'Global Factor Product A',
        })
        cls.product_b = cls.env['product.product'].create({
            'name': 'Global Factor Product B',
        })

    def _create_order(self, global_factor, product_line_vals):
        """Create a quotation with a header factor and inline product lines."""
        return self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'global_factor': global_factor,
            'order_line': [
                (0, 0, dict(vals))
                for vals in product_line_vals
            ],
        })

    def _line_vals(self, product=None, **extra):
        vals = {
            'product_id': (product or self.product_a).id,
            'product_uom_qty': 2.0,
        }
        vals.update(extra)
        return vals

    def _persisted_factors(self, lines):
        """Read line factors back from the database, bypassing the cache."""
        self.env['sale.order.line'].flush_recordset(['factor'])
        self.env['sale.order.line'].invalidate_cache(['factor'])
        return [line.factor for line in lines]

    def test_create_with_header_factor_applies_to_all_inline_lines(self):
        order = self._create_order(1.25, [
            self._line_vals(self.product_a),
            self._line_vals(self.product_b),
        ])
        self.assertEqual(len(order.order_line), 2)
        self.assertEqual(order.global_factor, 1.25)
        self.assertEqual(
            self._persisted_factors(order.order_line),
            [1.25, 1.25],
            'every inline product line must persist the header factor',
        )

    def test_lines_appended_later_inherit_current_header_factor(self):
        order = self._create_order(1.25, [self._line_vals(self.product_a)])

        order.write({'order_line': [
            (0, 0, self._line_vals(self.product_b)),
        ]})
        self.assertEqual(
            self._persisted_factors(order.order_line),
            [1.25, 1.25],
            'a later appended line must inherit the header factor '
            'without toggling or re-applying it',
        )

        # a final appended line through a different write path
        self.env['sale.order.line'].create({
            'order_id': order.id,
            'product_id': self.product_a.id,
            'product_uom_qty': 3.0,
        })
        self.assertEqual(
            self._persisted_factors(order.order_line),
            [1.25, 1.25, 1.25],
            'the final appended line must also inherit the header factor',
        )

    def test_header_factor_change_updates_all_existing_lines(self):
        order = self._create_order(1.25, [
            self._line_vals(self.product_a),
            self._line_vals(self.product_b),
        ])

        order.write({'global_factor': 4.0})
        self.assertEqual(
            self._persisted_factors(order.order_line),
            [4.0, 4.0],
            'changing the header factor must update existing lines server-side',
        )

        order.write({'global_factor': 0.0})
        self.assertEqual(
            self._persisted_factors(order.order_line),
            [0.0, 0.0],
            'a zero header factor must propagate to keep the zero-factor '
            'calculation semantics intact',
        )
        first_line = order.order_line[0]
        first_line.write({
            'purchase_price_estimate': 80.0,
            'line_factor': 2.0,
        })
        self.env['sale.order.line'].flush_recordset(['estimate_unit_price'])
        self.assertEqual(
            first_line.estimate_unit_price,
            160.0,
            'with factor 0 the estimate must fall back to the branch without '
            'the factor multiplication',
        )

    def test_line_factor_stays_independent_and_drives_estimate_price(self):
        order = self._create_order(1.25, [self._line_vals(self.product_a)])
        line = order.order_line[0]

        line.write({'purchase_price_estimate': 80.0, 'line_factor': 1.5})
        self.env['sale.order.line'].flush_recordset(['estimate_unit_price'])
        self.assertEqual(line.estimate_unit_price, 150.0)

        line.write({'line_factor': 2.0})
        self.env['sale.order.line'].flush_recordset(
            ['line_factor', 'estimate_unit_price'])
        self.env['sale.order.line'].invalidate_cache(
            ['line_factor', 'estimate_unit_price'])
        self.assertEqual(line.line_factor, 2.0)
        self.assertEqual(
            line.estimate_unit_price,
            200.0,
            'line_factor must remain editable and affect estimate_unit_price',
        )
        self.assertEqual(
            self._persisted_factors(line),
            [1.25],
            'editing line_factor must not touch the header-derived factor',
        )

    def test_copy_takes_copied_header_and_ignores_stale_line_snapshots(self):
        original = self._create_order(1.25, [
            self._line_vals(self.product_a),
            self._line_vals(self.product_b),
        ])
        # simulate legacy drifted rows directly in SQL
        self.env.cr.execute(
            "UPDATE sale_order_line SET factor = %s WHERE id IN %s",
            [99.0, tuple(original.order_line.ids)],
        )
        self.env['sale.order.line'].invalidate_cache(['factor'])
        self.assertEqual(
            self._persisted_factors(original.order_line),
            [99.0, 99.0],
            'precondition: legacy rows with drifted factors exist',
        )

        copy = original.copy()
        self.assertEqual(copy.global_factor, 1.25)
        self.assertEqual(
            self._persisted_factors(copy.order_line),
            [1.25, 1.25],
            'copied lines must take the copied header factor, not stale '
            'per-line snapshots',
        )

        copy.write({'global_factor': 3.0})
        self.assertEqual(
            self._persisted_factors(copy.order_line),
            [3.0, 3.0],
            'copied lines must follow their own copied header afterwards',
        )

    def test_conflicting_factor_values_cannot_create_drift(self):
        order = self._create_order(1.25, [self._line_vals(self.product_a)])
        first_line = order.order_line[0]

        standalone = self.env['sale.order.line'].create({
            'order_id': order.id,
            'product_id': self.product_b.id,
            'product_uom_qty': 1.0,
            'factor': 88.0,
        })
        self.assertEqual(
            self._persisted_factors(standalone), [1.25],
            'an explicit conflicting factor at create must be discarded',
        )

        order.write({'order_line': [
            (0, 0, self._line_vals(self.product_b, factor=77.0)),
        ]})
        appended = order.order_line.filtered(
            lambda l: l.product_id == self.product_b)[0]
        self.assertEqual(
            self._persisted_factors(appended), [1.25],
            'an inline command carrying a conflicting factor must be '
            'normalized to the header factor',
        )

        result = first_line.write({'factor': 55.0})
        self.assertTrue(result)
        self.assertEqual(
            self._persisted_factors(first_line), [1.25],
            'a direct conflicting factor write must not leave drift behind',
        )

        order.write({
            'global_factor': 2.5,
            'order_line': [(1, first_line.id, {'factor': 123.0})],
        })
        self.assertEqual(order.global_factor, 2.5)
        self.assertEqual(
            self._persisted_factors(first_line), [2.5],
            'in one save the new header factor wins over any conflicting '
            'line-level factor value',
        )
