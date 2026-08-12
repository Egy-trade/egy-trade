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
        cls.accounting_manager = cls.env['res.users'].create({
            'name': 'Finance controls accounting manager',
            'login': 'finance.controls.accounting.manager@example.test',
            'groups_id': [(6, 0, [
                cls.env.ref('base.group_user').id,
                cls.env.ref('sales_team.group_sale_salesman').id,
                cls.env.ref('account.group_account_manager').id,
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

    def _standard_tax_fixture(self):
        """Create isolated Finance-owned taxes, account and reporting tag."""
        income = self.env['account.account'].create({
            'name': 'UAT finance sales income', 'code': 'UATFINSAL',
            'account_type': 'income', 'company_id': self.company.id,
        })
        retention_account = self.env['account.account'].create({
            'name': 'UAT finance withholding receivable', 'code': 'UATFINRET',
            'account_type': 'asset_current', 'company_id': self.company.id,
        })
        tag = self.env['account.account.tag'].create({
            'name': 'UAT finance withholding tag', 'applicability': 'taxes',
        })
        vat = self.env['account.tax'].create({
            'name': 'UAT finance VAT 14', 'amount_type': 'percent', 'amount': 14.0,
            'type_tax_use': 'sale', 'company_id': self.company.id,
        })
        retention = self.env['account.tax'].create({
            'name': 'UAT finance retention 1', 'amount_type': 'percent', 'amount': -1.0,
            'type_tax_use': 'sale', 'company_id': self.company.id,
            'invoice_repartition_line_ids': [
                (0, 0, {'repartition_type': 'base', 'factor_percent': 100.0}),
                (0, 0, {'repartition_type': 'tax', 'factor_percent': 100.0,
                        'account_id': retention_account.id,
                        'tag_ids': [(6, 0, [tag.id])]}),
            ],
            'refund_repartition_line_ids': [
                (0, 0, {'repartition_type': 'base', 'factor_percent': 100.0}),
                (0, 0, {'repartition_type': 'tax', 'factor_percent': 100.0,
                        'account_id': retention_account.id,
                        'tag_ids': [(6, 0, [tag.id])]}),
            ],
        })
        original = {
            'quotation_vat_tax_id': self.company.quotation_vat_tax_id.id,
            'quotation_retention_tax_id': self.company.quotation_retention_tax_id.id,
            'property_account_income_id': self.product.product_tmpl_id.property_account_income_id.id,
        }
        self.company.write({
            'quotation_vat_tax_id': vat.id,
            'quotation_retention_tax_id': retention.id,
        })
        self.product.product_tmpl_id.write({'property_account_income_id': income.id})
        return vat, retention, retention_account, tag, original

    def _restore_standard_tax_fixture(self, original):
        self.company.write({
            'quotation_vat_tax_id': original['quotation_vat_tax_id'],
            'quotation_retention_tax_id': original['quotation_retention_tax_id'],
        })
        self.product.product_tmpl_id.write({
            'property_account_income_id': original['property_account_income_id'],
        })

    def _invoice_from_order(self, order):
        invoice = self.env['account.move'].create(order._prepare_invoice())
        invoice.write({'invoice_line_ids': [(0, 0, line._prepare_invoice_line())
                                            for line in order.order_line
                                            if not line.display_type]})
        return invoice

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
        with self.assertRaises(UserError):
            line.write({'tax_id': [(6, 0, [])]})
        with self.assertRaises(AccessError):
            line.write({'free_of_charge_authorized_by': self.env.user.id})
        with self.assertRaises(AccessError):
            self._line(
                order, free_of_charge_authorized_by=self.env.user.id,
            )

    def test_unconfigured_company_preserves_standard_odoo_line_tax_behavior(self):
        """Do not break optional modules such as sale_account_taxcloud."""
        old_vat = self.company.quotation_vat_tax_id
        old_retention = self.company.quotation_retention_tax_id
        self.company.write({
            'quotation_vat_tax_id': False,
            'quotation_retention_tax_id': False,
        })
        try:
            order = self._order()
            line = self._line(order, tax_id=[(6, 0, [old_vat.id])])
            self.assertEqual(line.tax_id, old_vat)
            line.write({'tax_id': [(6, 0, [old_retention.id])]})
            self.assertEqual(line.tax_id, old_retention)
        finally:
            self.company.write({
                'quotation_vat_tax_id': old_vat.id,
                'quotation_retention_tax_id': old_retention.id,
            })

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
            'refund_repartition_line_ids': [
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

    def test_standard_invoice_preserves_retention_evidence_and_tax_reporting(self):
        vat, retention, retention_account, tag, original = self._standard_tax_fixture()
        try:
            order = self._order()
            self._line(order, price_unit=100.0)
            order.write({'tax_treatment': 'standard'})
            invoice = self._invoice_from_order(order)
            retention_line = invoice.line_ids.filtered(
                lambda line: line.tax_repartition_line_id.tax_id == retention
            )
            self.assertEqual(invoice.quotation_tax_treatment, 'standard')
            self.assertEqual(invoice.quotation_retention_tax_id, retention)
            self.assertAlmostEqual(invoice.quotation_retention_basis, 100.0)
            self.assertAlmostEqual(invoice.quotation_retention_amount, -1.0)
            self.assertEqual(retention_line.account_id, retention_account)
            self.assertIn(tag, retention_line.tax_tag_ids)
            self.assertAlmostEqual(invoice.amount_total, 113.0)
            self.assertEqual(order.order_line.tax_id, vat | retention)
        finally:
            self._restore_standard_tax_fixture(original)

    def test_credit_note_reversal_preserves_and_reverses_retention(self):
        _vat, retention, retention_account, tag, original = self._standard_tax_fixture()
        try:
            order = self._order()
            self._line(order, price_unit=100.0)
            order.write({'tax_treatment': 'standard'})
            invoice = self._invoice_from_order(order)
            invoice.action_post()
            reversal = invoice._reverse_moves(default_values_list=[{'ref': 'UAT-FIN retention reversal'}], cancel=False)
            original_retention = invoice.line_ids.filtered(
                lambda line: line.tax_repartition_line_id.tax_id == retention
            )
            reversal_retention = reversal.line_ids.filtered(
                lambda line: line.tax_repartition_line_id.tax_id == retention
            )
            self.assertEqual(reversal.move_type, 'out_refund')
            self.assertEqual(reversal.quotation_tax_treatment, 'standard')
            self.assertEqual(reversal.quotation_retention_tax_id, retention)
            self.assertAlmostEqual(reversal.quotation_retention_basis, -100.0)
            self.assertAlmostEqual(reversal.quotation_retention_amount, 1.0)
            self.assertEqual(reversal_retention.account_id, retention_account)
            self.assertIn(tag, reversal_retention.tax_tag_ids)
            self.assertAlmostEqual(reversal_retention.balance, -original_retention.balance)
        finally:
            self._restore_standard_tax_fixture(original)

    def test_eur_equivalent_threshold_requires_approval_at_exact_boundary(self):
        eur = self.env.ref('base.EUR')
        pricelist = self.env['product.pricelist'].create({
            'name': 'UAT finance EUR threshold', 'currency_id': eur.id,
        })
        at_threshold = self._order()
        at_threshold.write({'pricelist_id': pricelist.id, 'tax_treatment': 'cif_no_taxes'})
        self._line(at_threshold, price_unit=100000.0)
        self.assertIn('high_value', at_threshold._finance_requirement_codes())
        below_threshold = self._order()
        below_threshold.write({'pricelist_id': pricelist.id, 'tax_treatment': 'cif_no_taxes'})
        self._line(below_threshold, price_unit=99999.99)
        self.assertNotIn('high_value', below_threshold._finance_requirement_codes())

    def test_decimal_discount_rounds_vat_and_retention_on_invoice(self):
        _vat, retention, _retention_account, _tag, original = self._standard_tax_fixture()
        try:
            order = self._order()
            line = self._line(order, price_unit=100.03)
            order.write({'tax_treatment': 'standard'})
            line.write({'discount_2': 10.0})
            invoice = self._invoice_from_order(order)
            retention_line = invoice.line_ids.filtered(
                lambda move_line: move_line.tax_repartition_line_id.tax_id == retention
            )
            self.assertAlmostEqual(invoice.amount_untaxed, 90.03)
            self.assertEqual(
                invoice.quotation_retention_basis,
                invoice.currency_id.round(invoice.amount_untaxed),
            )
            self.assertAlmostEqual(invoice.quotation_retention_amount, -0.90)
            self.assertEqual(
                invoice.quotation_retention_amount,
                invoice.currency_id.round(-0.9003),
            )
            self.assertAlmostEqual(retention_line.balance, 0.90)
            self.assertAlmostEqual(invoice.amount_total, 101.73)
        finally:
            self._restore_standard_tax_fixture(original)

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

    def test_standard_tax_requires_refund_account_and_reporting_tag(self):
        account = self.env['account.account'].create({
            'name': 'Refund validation receivable', 'code': 'QRETFUND',
            'account_type': 'asset_current', 'company_id': self.company.id,
        })
        tag = self.env['account.account.tag'].create({
            'name': 'Refund validation tag', 'applicability': 'taxes',
        })
        vat = self.env['account.tax'].create({
            'name': 'Refund validation VAT', 'amount_type': 'percent', 'amount': 14.0,
            'type_tax_use': 'sale', 'company_id': self.company.id,
        })
        retention = self.env['account.tax'].create({
            'name': 'Refund validation retention', 'amount_type': 'percent', 'amount': -1.0,
            'type_tax_use': 'sale', 'company_id': self.company.id,
            'invoice_repartition_line_ids': [
                (0, 0, {'repartition_type': 'base', 'factor_percent': 100.0}),
                (0, 0, {'repartition_type': 'tax', 'factor_percent': 100.0,
                        'account_id': account.id, 'tag_ids': [(6, 0, [tag.id])]}),
            ],
        })
        original_vat = self.company.quotation_vat_tax_id
        original_retention = self.company.quotation_retention_tax_id
        self.company.write({
            'quotation_vat_tax_id': vat.id,
            'quotation_retention_tax_id': retention.id,
        })
        try:
            order = self._order()
            with self.assertRaises(ValidationError):
                order._finance_tax_ids()
        finally:
            self.company.write({
                'quotation_vat_tax_id': original_vat.id,
                'quotation_retention_tax_id': original_retention.id,
            })

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

    def test_accounting_manager_can_audit_validity_override(self):
        order = self._order()
        target_days = order.company_id.quotation_expiry_days_default + 2
        order.with_user(self.accounting_manager).write({
            'offer_expiry_days': target_days,
            'finance_approval_reason': 'Accounting approved tender validity.',
        })
        self.assertEqual(order.offer_expiry_days, target_days)
        self.assertTrue(order.message_ids.filtered(
            lambda message: 'Accounting approved tender validity.' in (message.body or '')
        ))
