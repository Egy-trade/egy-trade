# -*- coding: utf-8 -*-

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import SavepointCase


class TestQuotationFinanceControls(SavepointCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env.ref('base.res_partner_1')
        cls.company = cls.env.company
        cls.product = cls.env['product.product'].create({
            'name': 'Quotation finance control product', 'sale_ok': True,
            'purchase_ok': True, 'list_price': 100.0,
        })
        cls.salesperson = cls.env['res.users'].create({
            'name': 'Finance controls salesperson',
            'login': 'finance.controls.salesperson@example.test',
            'groups_id': [(6, 0, [
                cls.env.ref('base.group_user').id,
                cls.env.ref('sales_team.group_sale_salesman').id,
            ])],
        })

    def _order(self, owner=None):
        values = {'partner_id': self.partner.id}
        if owner:
            values['user_id'] = owner.id
        order = self.env['sale.order'].create(values)
        if hasattr(order, '_record_commercial_change'):
            order._record_commercial_change('update_today')
        return order

    def _line(self, order, **values):
        defaults = {
            'order_id': order.id, 'product_id': self.product.id,
            'name': self.product.display_name, 'product_uom_qty': 1.0,
            'price_unit': 100.0,
        }
        defaults.update(values)
        return self.env['sale.order.line'].create(defaults)

    def test_issue_blocks_zero_price_until_authorized_foc_with_reason(self):
        order = self._order()
        order.write({'tax_treatment': 'cif_no_taxes'})
        line = self._line(order, price_unit=0.0)
        with self.assertRaises(UserError):
            order._check_finance_issue_requirements()
        line.write({'is_free_of_charge': True, 'free_of_charge_reason': 'Approved sample'})
        self.assertEqual(line.free_of_charge_authorized_by, self.env.user)
        self.assertTrue(line.free_of_charge_authorized_at)
        self.assertTrue(order._check_finance_issue_requirements())

    def test_foc_and_direct_tax_import_bypasses_are_rejected(self):
        order = self._order()
        with self.assertRaises(ValidationError):
            self._line(order, price_unit=0.0, is_free_of_charge=True)
        line = self._line(order, tax_id=[(6, 0, [])])
        self.assertFalse(line.tax_id)
        with self.assertRaises(AccessError):
            line.write({'free_of_charge_authorized_by': self.env.user.id})
        with self.assertRaises(AccessError):
            self._line(
                order, free_of_charge_authorized_by=self.env.user.id,
            )

    def test_salesperson_selecting_cif_gets_safe_no_tax_default_and_audit(self):
        cif = self.env['account.incoterms'].search([('code', '=', 'CIF')], limit=1)
        if not cif:
            cif = self.env['account.incoterms'].create({
                'name': 'CIF finance-control test', 'code': 'CIF',
            })
        order = self._order(owner=self.salesperson)
        self._line(order)
        order.with_user(self.salesperson).write({
            'incoterm': cif.id,
            'tax_treatment': 'cif_no_taxes',
        })
        self.assertEqual(order.tax_treatment, 'cif_no_taxes')
        self.assertFalse(order.order_line.tax_id)
        self.assertTrue(order.message_ids.filtered(
            lambda message: 'Tax Treatment changed' in (message.body or '')
        ))

    def test_manual_price_requires_and_records_manager_approval(self):
        order = self._order()
        order.write({'tax_treatment': 'cif_no_taxes'})
        line = self._line(order)
        line.write({'price_unit': 125.0})
        self.assertIn('manual_price', order._finance_requirement_codes())
        with self.assertRaises(UserError):
            order._check_finance_issue_requirements()
        order.write({'finance_approval_reason': 'Margin exception reviewed.'})
        order.action_approve_finance_requirements()
        self.assertTrue(order.finance_approval_ids.filtered(lambda item: item.code == 'manual_price'))
        with self.assertRaises(AccessError):
            self.env['sale.order.finance.approval'].create({
                'order_id': order.id, 'code': 'forged', 'label': 'Forged',
                'approver_id': self.env.user.id, 'reason': 'RPC bypass',
            })
        with self.assertRaises(AccessError):
            order.finance_approval_ids.write({'invalidated': False})
        with self.assertRaises(AccessError):
            order.finance_approval_ids.unlink()
        self.assertTrue(order._check_finance_issue_requirements())
        line.write({'price_unit': 126.0})
        self.assertTrue(order.finance_approval_ids.filtered('invalidated'))
        with self.assertRaises(UserError):
            order._check_finance_issue_requirements()

    def test_standard_vat_and_retention_total_and_cif_removal(self):
        account = self.env['account.account'].create({
            'name': 'Withholding receivable test', 'code': 'QRETTEST',
            'account_type': 'asset_current', 'company_id': self.company.id,
        })
        tag = self.env['account.account.tag'].create({'name': 'Withholding test tag', 'applicability': 'taxes'})
        vat = self.env['account.tax'].create({
            'name': 'Quotation VAT 14 test', 'amount_type': 'percent', 'amount': 14.0,
            'type_tax_use': 'sale', 'company_id': self.company.id,
        })
        retention = self.env['account.tax'].create({
            'name': 'Quotation retention 1 test', 'amount_type': 'percent', 'amount': -1.0,
            'type_tax_use': 'sale', 'company_id': self.company.id,
            'invoice_repartition_line_ids': [
                (0, 0, {'repartition_type': 'base', 'factor_percent': 100.0}),
                (0, 0, {'repartition_type': 'tax', 'factor_percent': 100.0,
                        'account_id': account.id, 'tag_ids': [(6, 0, [tag.id])]}),
            ],
        })
        old_vat, old_retention = self.company.quotation_vat_tax_id, self.company.quotation_retention_tax_id
        self.company.write({'quotation_vat_tax_id': vat.id, 'quotation_retention_tax_id': retention.id})
        try:
            order = self._order()
            line = self._line(order)
            order.write({'tax_treatment': 'standard'})
            self.assertAlmostEqual(order.amount_untaxed, 100.0)
            self.assertAlmostEqual(order.amount_tax, 13.0)
            self.assertAlmostEqual(order.amount_total, 113.0)
            self.assertEqual(line.tax_id, vat | retention)
            line.write({'discount_2': 10.0})
            self.assertAlmostEqual(order.amount_untaxed, 90.0)
            self.assertAlmostEqual(order.amount_tax, 11.7)
            self.assertAlmostEqual(order.amount_total, 101.7)
            line.write({'discount_2': 0.0})
            order.write({'tax_treatment': 'cif_no_taxes'})
            self.assertFalse(line.tax_id)
            self.assertAlmostEqual(order.amount_total, 100.0)
        finally:
            self.company.write({
                'quotation_vat_tax_id': old_vat.id,
                'quotation_retention_tax_id': old_retention.id,
            })

    def test_cif_and_invoice_preserve_tax_treatment(self):
        order = self._order()
        order.write({'tax_treatment': 'cif_no_taxes'})
        invoice_values = order._prepare_invoice()
        self.assertEqual(invoice_values['quotation_tax_treatment'], 'cif_no_taxes')
        self.assertFalse(invoice_values['quotation_retention_tax_id'])

    def test_standard_issue_requires_configured_matching_taxes(self):
        order = self._order()
        self._line(order)
        with self.assertRaises(UserError):
            order._check_finance_issue_requirements()

    def test_validity_override_requires_manager_reason_and_is_audited(self):
        order = self._order()
        target_days = order.company_id.quotation_expiry_days_default + 1
        with self.assertRaises(ValidationError):
            order.write({'offer_expiry_days': target_days})
        order.write({
            'offer_expiry_days': target_days,
            'finance_approval_reason': 'Client tender requires a longer validity period.',
        })
        self.assertEqual(order.offer_expiry_days, target_days)
        self.assertTrue(order.message_ids.filtered(
            lambda message: 'Days of Expiry overridden' in (message.body or '')
        ))
