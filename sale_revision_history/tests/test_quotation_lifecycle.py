# -*- coding: utf-8 -*-

from unittest.mock import patch

from lxml import etree

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import SavepointCase

from ..models.sale_order import (
    _LIFECYCLE_INTERNAL_TOKEN,
    _WITHHOLDING_CONFIRMATION_TOKEN,
)
from odoo.addons.sale_order_product_pricing.models.sale_order import (
    _PRICING_INTERNAL_TOKEN,
)


class QuotationLifecycleCase(SavepointCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env.ref("base.res_partner_1")
        cls.product = cls.env["product.product"].create({
            "name": "Lifecycle product", "sale_ok": True, "list_price": 100.0,
            "invoice_policy": "order",
        })
        cls.vat_tax = cls.env["account.tax"].create({
            "name": "Lifecycle VAT 14%", "amount": 14.0, "amount_type": "percent",
            "type_tax_use": "sale", "company_id": cls.env.company.id,
        })
        cls.withholding_tax = cls.env["account.tax"].create({
            "name": "Lifecycle Withholding 1%", "amount": -1.0, "amount_type": "percent",
            "type_tax_use": "sale", "company_id": cls.env.company.id,
        })
        cls.env.company.sudo().write({
            "quotation_vat_tax_id": cls.vat_tax.id,
            "quotation_retention_tax_id": cls.withholding_tax.id,
        })
        cls.receivable_account = cls.env["account.account"].create({
            "name": "Lifecycle Test Receivable",
            "code": "LTREC",
            "account_type": "asset_receivable",
            "reconcile": True,
            "company_id": cls.env.company.id,
        })
        cls.income_account = cls.env["account.account"].create({
            "name": "Lifecycle Test Sales",
            "code": "LTINC",
            "account_type": "income",
            "company_id": cls.env.company.id,
        })
        cls.env["account.journal"].create({
            "name": "Lifecycle Test Sales Journal",
            "code": "LTSJ",
            "type": "sale",
            "company_id": cls.env.company.id,
            "default_account_id": cls.income_account.id,
        })
        cls.tax_account = cls.env["account.account"].create({
            "name": "Lifecycle Test Tax",
            "code": "LTTAX",
            "account_type": "liability_current",
            "company_id": cls.env.company.id,
        })
        for tax in cls.vat_tax | cls.withholding_tax:
            tax.invoice_repartition_line_ids.filtered(
                lambda line: line.repartition_type == "tax"
            ).account_id = cls.tax_account
            tax.refund_repartition_line_ids.filtered(
                lambda line: line.repartition_type == "tax"
            ).account_id = cls.tax_account
        cls.partner.with_company(cls.env.company).property_account_receivable_id = (
            cls.receivable_account
        )
        cls.product.property_account_income_id = cls.income_account
        cls.salesperson = cls.env["res.users"].create({
            "name": "Lifecycle Salesperson",
            "login": "lifecycle.salesperson@example.test",
            "email": "lifecycle.salesperson@example.test",
            "groups_id": [(6, 0, [
                cls.env.ref("base.group_user").id,
                cls.env.ref("sales_team.group_sale_salesman").id,
            ])],
        })
        cls.quotation_specialist = cls.env["res.users"].create({
            "name": "Lifecycle Quotation Specialist",
            "login": "lifecycle.qs@example.test",
            "groups_id": [(6, 0, [
                cls.env.ref("base.group_user").id,
                cls.env.ref("sales_team.group_sale_salesman").id,
                cls.env.ref(
                    "sale_order_product_pricing.quotation_specialist_group"
                ).id,
            ])],
        })
        cls.quotation_manager = cls.env["res.users"].create({
            "name": "Lifecycle Quotation Manager",
            "login": "lifecycle.quotation.manager@example.test",
            "groups_id": [(6, 0, [
                cls.env.ref("base.group_user").id,
                cls.env.ref(
                    "sale_order_product_pricing.quotation_manager_group"
                ).id,
            ])],
        })

    def _draft(self, **extra):
        values = {
            "partner_id": self.partner.id,
            "user_id": self.salesperson.id,
            "global_factor": 1.40,
            "order_line": [(0, 0, {
                "product_id": self.product.id,
                "name": self.product.display_name,
                "product_uom_qty": 2.0,
                "price_unit": 100.0,
                "sn": "A-01",
            })],
        }
        values.update(extra)
        return self.env["sale.order"].create(values)

    def test_assigned_salesperson_can_edit_draft_without_daily_wizard(self):
        order = self._draft()
        line = order.order_line.with_user(self.salesperson)
        order.with_user(self.salesperson).write({"note": "Draft edited directly"})
        line.write({"name": "Draft line edited directly"})
        self.assertEqual(order.note, "Draft edited directly")
        self.assertEqual(line.name, "Draft line edited directly")

    def test_add_below_is_disabled_to_preserve_active_line_position(self):
        order = self._draft()
        source = order.order_line
        with self.assertRaises(UserError):
            source.action_add_below()

    def test_draft_header_edit_needs_no_daily_decision(self):
        order = self._draft()
        original_date_order = order.date_order
        order.write({"note": "Commercial change without a daily decision"})
        self.assertEqual(order.date_order, original_date_order)
        self.assertEqual(order.note, "Commercial change without a daily decision")

    def test_vat_change_fingerprint_handles_virtual_onchange_lines(self):
        """Approval recomputation must support Odoo's NewId line records."""
        order = self.env["sale.order"].new({
            "partner_id": self.partner.id,
            "apply_vat": True,
            "order_line": [(0, 0, {
                "product_id": self.product.id,
                "name": self.product.display_name,
                "product_uom_qty": 1.0,
                "price_unit": 100.0,
            })],
        })
        before = order._commercial_fingerprint()
        order.apply_vat = False
        order.vat_exemption_reason = "Exempt customer"
        after = order._commercial_fingerprint()

        self.assertNotEqual(before, after)
        self.assertIsInstance(order.finance_approval_required, bool)

    def test_direct_line_orm_create_write_unlink_are_free_in_draft_and_lock_sent(self):
        order = self._draft()
        source = order.order_line
        line_model = self.env["sale.order.line"].with_context(import_file=True)
        added = line_model.create({
            "order_id": order.id,
            "product_id": self.product.id,
            "name": "Imported product line",
        })
        source.with_context(import_file=True).write({"name": "Draft RPC change"})
        added.with_context(import_file=True).unlink()

        order.with_context(
            _lifecycle_internal_token=_LIFECYCLE_INTERNAL_TOKEN,
        ).write({"state": "sent"})
        for operation in (
                lambda: line_model.create({
                    "order_id": order.id,
                    "product_id": self.product.id,
                    "name": "Forbidden import line",
                }),
                lambda: source.with_context(import_file=True).write({"name": "Forbidden RPC change"}),
                lambda: source.with_context(import_file=True).unlink()):
            with self.assertRaises(UserError):
                operation()

    def test_initial_nested_create_needs_no_daily_decision(self):
        order = self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "order_line": [(0, 0, {
                "product_id": self.product.id,
                "name": self.product.display_name,
                "product_uom_qty": 1.0,
            })],
        })
        self.assertEqual(order.order_line.tax_id, self.vat_tax)

    def test_sent_quote_revision_archives_source_and_opens_successor(self):
        order = self._draft()
        order.with_context(_lifecycle_internal_token=_LIFECYCLE_INTERNAL_TOKEN).write({"state": "sent"})
        action = order.action_view_revision_wizard("Customer requested a revised commercial option.")
        revision = self.env["sale.order"].browse(action["res_id"])
        self.assertFalse(order.active)
        self.assertEqual(order.current_revision_id, revision)
        self.assertEqual(revision.state, "draft")
        self.assertEqual(revision.revision_number, 1)
        self.assertIn(order.name, revision.name)

    def test_optional_products_are_free_to_edit_in_draft(self):
        order = self._draft()
        option = self.env["sale.order.option"].create({
            "order_id": order.id,
            "product_id": self.product.id,
            "name": "Draft optional product",
            "quantity": 1.0,
            "uom_id": self.product.uom_id.id,
            "price_unit": 10.0,
        })
        option.write({"name": "Edited draft optional product"})
        self.assertEqual(option.name, "Edited draft optional product")
        option.unlink()

    def test_preview_and_read_do_not_mutate_quotation(self):
        order = self._draft(product_pricing=True)
        order.order_line.with_context(
            _lifecycle_internal_token=_LIFECYCLE_INTERNAL_TOKEN,
        ).write({"purchase_price_estimate": 50.0})
        original = (
            order.write_date,
            order.product_pricing_preview_hash,
            order.product_pricing_previewed_at,
            order.pricing_audit_log_ids.ids,
        )
        order.read(["name", "offer_date", "amount_total"])
        order.action_preview_product_pricing()
        self.assertEqual(
            (
                order.write_date,
                order.product_pricing_preview_hash,
                order.product_pricing_previewed_at,
                order.pricing_audit_log_ids.ids,
            ),
            original,
        )

    def test_issue_offer_attaches_audits_and_locks_all_mutation_paths(self):
        order = self._draft()
        report_service = self.env["ir.actions.report"]
        with patch.object(
                type(report_service), "_render_qweb_pdf",
                return_value=(b"%PDF-test", "pdf")) as render:
            order.action_issue_offer_pdf()
        render.assert_called_once_with("sale.action_report_saleorder", order.ids)
        self.assertEqual(order.state, "sent")
        self.assertTrue(order.issued_offer_attachment_id)
        self.assertEqual(order.issued_offer_attachment_id.mimetype, "application/pdf")
        self.assertEqual(order.issued_offer_by, self.env.user)
        self.assertEqual(order.issued_offer_version, order.name)
        self.assertIn("Issued customer Offer PDF", order.issued_offer_audit)
        # Reading/recomputing totals is not a commercial mutation.  Legacy
        # quotation total computes must use cache assignments rather than
        # re-entering ``sale.order.write`` on a locked Sent offer.
        expected_totals = (
            order.amount_untaxed, order.amount_tax,
            order.amount_discount, order.amount_total,
        )
        order.invalidate_cache([
            "amount_untaxed", "amount_tax", "amount_discount", "amount_total",
        ])
        order._amount_all()
        totals = order.read([
            "amount_untaxed", "amount_tax", "amount_discount", "amount_total",
        ])[0]
        self.assertEqual(order.state, "sent")
        self.assertEqual(
            tuple(totals[field_name] for field_name in (
                "amount_untaxed", "amount_tax", "amount_discount", "amount_total",
            )),
            expected_totals,
        )
        with self.assertRaises(UserError):
            order.write({"note": "RPC mutation"})
        with self.assertRaises(UserError):
            order.order_line.write({"name": "Import mutation"})
        with self.assertRaises(UserError):
            order.action_quotation_send()

    def test_confirmation_requires_the_withholding_dialog_then_confirms_without_invoice(self):
        order = self._draft()
        report_service = self.env["ir.actions.report"]
        with patch.object(
                type(report_service), "_render_qweb_pdf",
                return_value=(b"%PDF-test", "pdf")):
            order.action_issue_offer_pdf()
        with self.assertRaises(UserError):
            order.write({"state": "sale"})
        action = order.action_confirm()
        self.assertEqual(action["res_model"], "sale.order.withholding.confirmation")
        before_moves = self.env["account.move"].search_count([
            ("invoice_origin", "=", order.name),
        ])
        before_all_moves = self.env["account.move"].search_count([])
        before_move_lines = self.env["account.move.line"].search_count([])
        self.env["sale.order.withholding.confirmation"].with_context(
            **action["context"],
        ).create({"sale_id": order.id, "decision": "no"}).action_confirm()
        self.assertEqual(order.state, "sale")
        self.assertEqual(order.withholding_confirmation, "no")
        self.assertEqual(self.env["account.move"].search_count([
            ("invoice_origin", "=", order.name),
        ]), before_moves)
        self.assertEqual(self.env["account.move"].search_count([]), before_all_moves)
        self.assertEqual(
            self.env["account.move.line"].search_count([]), before_move_lines,
        )

        # Invoicing remains a later, explicit standard Odoo action.  When it
        # is performed, the final Sales Order line tax selection is inherited.
        invoice = order._create_invoices()
        self.assertEqual(invoice.state, "draft")
        invoice_product_line = invoice.invoice_line_ids.filtered(
            lambda line: line.product_id == self.product
        )
        self.assertEqual(invoice_product_line.tax_ids, order.order_line.tax_id)

    def test_direct_confirmation_service_call_cannot_bypass_wizard(self):
        order = self._draft()
        report_service = self.env["ir.actions.report"]
        with patch.object(type(report_service), "_render_qweb_pdf", return_value=(b"%PDF-test", "pdf")):
            order.action_issue_offer_pdf()
        with self.assertRaises(AccessError):
            order._confirm_withholding_decision(False)

    def test_withholding_audit_fields_are_system_managed(self):
        order = self._draft()
        with self.assertRaises(AccessError):
            order.write({"withholding_confirmation": "no"})
        order.with_context(
            _lifecycle_internal_token=_LIFECYCLE_INTERNAL_TOKEN,
        ).write({"withholding_confirmation": "no"})
        self.assertEqual(order.withholding_confirmation, "no")

    def test_discount_approve_cannot_bypass_withholding_dialog(self):
        order = self._draft()
        report_service = self.env["ir.actions.report"]
        with patch.object(
                type(report_service), "_render_qweb_pdf",
                return_value=(b"%PDF-test", "pdf")):
            order.action_issue_offer_pdf()
        with self.assertRaises(UserError):
            order.action_approve()
        self.assertEqual(order.state, "sent")

    def test_retention_only_confirmation_creates_issued_successor_and_preserves_approval(self):
        order = self._draft(
            apply_withholding=False,
            quotation_specialist_id=self.quotation_specialist.id,
        )
        order.action_accept_sales_responsibility()
        order.with_user(
            self.quotation_manager
        ).action_approve_quotation_requirements()
        source_approval = order.finance_approval_ids.filtered(
            lambda approval: approval.code == "quotation_manager"
            and not approval.invalidated
        )
        self.assertEqual(len(source_approval), 1)
        report_service = self.env["ir.actions.report"]
        with patch.object(type(report_service), "_render_qweb_pdf", return_value=(b"%PDF-test", "pdf")):
            order.action_issue_offer_pdf()
            self.env["sale.order.withholding.confirmation"].create({
                "sale_id": order.id, "decision": "yes",
            }).action_confirm()
        revision = order.current_revision_id
        self.assertTrue(revision)
        self.assertTrue(revision.retention_only_revision)
        self.assertEqual(revision.retention_only_source_id, order)
        self.assertTrue(revision.apply_withholding)
        self.assertEqual(revision.state, "sale")
        self.assertTrue(revision.issued_offer_attachment_id)
        self.assertEqual(revision.withholding_confirmation, "yes")
        self.assertEqual(revision._commercial_fingerprint(), order._commercial_fingerprint())
        carried = revision.finance_approval_ids.filtered(
            lambda approval: approval.code == "quotation_manager"
            and not approval.invalidated
        )
        self.assertEqual(len(carried), 1)
        self.assertEqual(carried.carried_from_approval_id, source_approval)

    def test_retention_only_copy_preserves_issued_dates_and_vat_exception(self):
        """A delayed VAT-exempt offer must remain a byte-for-term clone.

        ``offer_date`` is deliberately copy=False for ordinary new drafts.
        Retention confirmation is different: it changes only 1% withholding,
        including for legacy historical-unverified price-origin lines.
        """
        order = self._draft(
            apply_vat=False,
            vat_exemption_reason="Customer exemption certificate on file",
            quotation_specialist_id=self.quotation_specialist.id,
        )
        estimate_currency = self.env["res.currency"].search([
            ("id", "!=", self.env.company.currency_id.id),
            ("active", "=", True),
        ], limit=1)
        self.assertTrue(estimate_currency)
        rate_values = {
            "currency_id": estimate_currency.id,
            "company_id": self.env.company.id,
            "name": "2024-01-15",
            "rate": 0.5,
        }
        existing_rate = self.env["res.currency.rate"].search([
            ("currency_id", "=", estimate_currency.id),
            ("company_id", "=", self.env.company.id),
            ("name", "=", "2024-01-15"),
        ], limit=1)
        if existing_rate:
            existing_rate.write({"rate": rate_values["rate"]})
        else:
            self.env["res.currency.rate"].create(rate_values)
        order.write({
            "date_order": "2024-01-15 09:30:00",
            "offer_date": "2024-01-15",
            "validity_date": "2024-01-29",
            "commitment_date": "2024-02-01 09:30:00",
            "currency_estimate_id": estimate_currency.id,
        })
        order.order_line.sudo().with_context(
            _pricing_internal_token=_PRICING_INTERNAL_TOKEN,
        ).write({
            "price_origin": "historical_unverified",
            "price_origin_verified": False,
            "price_origin_evidence": "legacy_unverified",
        })
        issued_fingerprint = order._commercial_fingerprint()
        order.action_accept_sales_responsibility()
        order.with_user(self.quotation_manager).action_approve_quotation_requirements()
        self.assertEqual(
            set(order.finance_approval_ids.mapped("code")),
            {"quotation_manager", "vat_exemption"},
        )
        report_service = self.env["ir.actions.report"]
        before_moves = self.env["account.move"].search_count([])
        before_move_lines = self.env["account.move.line"].search_count([])
        with patch.object(
                type(report_service), "_render_qweb_pdf",
                return_value=(b"%PDF-test", "pdf")), patch.object(
                    type(order), "action_confirm", return_value=True,
                ) as final_confirmation:
            order.action_issue_offer_pdf()
            self.env["sale.order.withholding.confirmation"].create({
                "sale_id": order.id, "decision": "yes",
            }).action_confirm()
        revision = order.current_revision_id
        # The automatic revision is now issued but deliberately paused before
        # standard SO confirmation.  This is the only point where its clone
        # snapshot can be compared to the issued source: action_confirm
        # correctly stamps a new confirmation date afterwards.
        self.assertEqual(revision.state, "sent")
        final_confirmation.assert_called_once()
        self.assertTrue(revision.apply_withholding)
        self.assertFalse(revision.apply_vat)
        self.assertEqual(revision.vat_exemption_reason, order.vat_exemption_reason)
        self.assertEqual(revision.date_order, order.date_order)
        self.assertEqual(revision.offer_date, order.offer_date)
        self.assertEqual(revision.validity_date, order.validity_date)
        self.assertEqual(revision.commitment_date, order.commitment_date)
        self.assertEqual(
            revision.currency_rate_estimate, order.currency_rate_estimate,
        )
        self.assertEqual(
            revision.currency_rate_inverse, order.currency_rate_inverse,
        )
        self.assertEqual(revision._commercial_fingerprint(), issued_fingerprint)
        self.assertEqual(
            revision.order_line.price_origin, "historical_unverified",
        )
        self.assertEqual(self.env["account.move"].search_count([]), before_moves)
        self.assertEqual(
            self.env["account.move.line"].search_count([]), before_move_lines,
        )

        revision.with_context(
            _withholding_confirmation_token=_WITHHOLDING_CONFIRMATION_TOKEN,
        ).action_confirm()
        self.assertEqual(revision.state, "sale")
        self.assertNotEqual(revision.date_order, order.date_order)
        self.assertEqual(self.env["account.move"].search_count([]), before_moves)
        self.assertEqual(
            self.env["account.move.line"].search_count([]), before_move_lines,
        )

    def test_retention_only_revision_preserves_free_of_charge_authorization(self):
        order = self._draft(apply_withholding=False)
        order.order_line.write({
            "price_unit": 0.0,
            "is_free_of_charge": True,
            "free_of_charge_reason": "Approved sample",
        })
        self.assertTrue(order.order_line._is_authorized_foc())
        report_service = self.env["ir.actions.report"]
        with patch.object(
                type(report_service), "_render_qweb_pdf",
                return_value=(b"%PDF-test", "pdf")):
            order.action_issue_offer_pdf()
            self.env["sale.order.withholding.confirmation"].create({
                "sale_id": order.id, "decision": "yes",
            }).action_confirm()
        revision = order.current_revision_id
        self.assertEqual(revision.state, "sale")
        self.assertTrue(revision.order_line._is_authorized_foc())
        self.assertEqual(
            revision.order_line.free_of_charge_authorized_by,
            order.order_line.free_of_charge_authorized_by,
        )

    def test_retention_confirmation_refuses_non_wizard_and_non_matching_copy(self):
        order = self._draft()
        report_service = self.env["ir.actions.report"]
        with patch.object(type(report_service), "_render_qweb_pdf", return_value=(b"%PDF-test", "pdf")):
            order.action_issue_offer_pdf()
            action = order.action_view_revision_wizard("Non-retention change")
        revision = self.env["sale.order"].browse(action["res_id"])
        revision.with_context(_lifecycle_internal_token=_LIFECYCLE_INTERNAL_TOKEN).write({
            "note": "Changed agreed commercial term",
        })
        from odoo.addons.sale_order_product_pricing.models.finance_controls import _RETENTION_REVISION_TOKEN
        with self.assertRaises(ValidationError):
            revision.with_context(
                _retention_revision_token=_RETENTION_REVISION_TOKEN,
            ).action_apply_retention_only_revision(
                order, order._commercial_fingerprint(), True,
            )

    def test_fingerprint_diagnostics_expose_paths_not_commercial_values(self):
        expected = {
            "partner": 7,
            "lines": [{
                "price_unit": 123.45,
                "name": "Confidential item",
            }],
        }
        actual = {
            "partner": 7,
            "lines": [{
                "price_unit": 120.00,
                "name": "Confidential item",
            }],
        }

        paths = self.env["sale.order"]._fingerprint_difference_paths(
            expected, actual,
        )

        self.assertEqual(paths, ["lines[0].price_unit"])
        self.assertNotIn("123.45", repr(paths))
        self.assertNotIn("Confidential item", repr(paths))

    def test_superseded_issued_offer_cannot_be_confirmed(self):
        order = self._draft()
        report_service = self.env['ir.actions.report']
        with patch.object(
                type(report_service), '_render_qweb_pdf',
                return_value=(b'%PDF-test', 'pdf')):
            order.action_issue_offer_pdf()
        order.action_view_revision_wizard('New customer revision')
        self.assertFalse(order.active)
        with self.assertRaises(UserError):
            order.action_confirm()

    def test_optional_product_cannot_be_created_on_issued_offer(self):
        order = self._draft()
        report_service = self.env['ir.actions.report']
        with patch.object(
                type(report_service), '_render_qweb_pdf',
                return_value=(b'%PDF-test', 'pdf')):
            order.action_issue_offer_pdf()
        with self.assertRaises(UserError):
            self.env['sale.order.option'].create({
                'order_id': order.id,
                'product_id': self.product.id,
                'name': 'Injected optional product',
                'quantity': 1.0,
                'uom_id': self.product.uom_id.id,
                'price_unit': 10.0,
            })

    def test_issue_without_sales_acceptance_is_audited_and_kpi_flagged(self):
        order = self._draft()
        report_service = self.env["ir.actions.report"]
        with patch.object(
                type(report_service), "_render_qweb_pdf",
                return_value=(b"%PDF-test", "pdf")):
            order.action_issue_offer_pdf()
        self.assertTrue(order.issued_without_sales_acceptance)
        self.assertIn("without Sales responsibility acceptance", order.issued_offer_audit)

        accepted = self._draft()
        accepted.action_accept_sales_responsibility()
        self.assertTrue(accepted.sales_responsibility_accepted)
        self.assertEqual(accepted.sales_responsibility_accepted_by, self.env.user)

    def test_accepted_sales_responsibility_issues_without_exception_flag_or_audit(self):
        order = self._draft(user_id=self.salesperson.id)
        order.action_accept_sales_responsibility()
        report_service = self.env["ir.actions.report"]
        with patch.object(
                type(report_service), "_render_qweb_pdf",
                return_value=(b"%PDF-test", "pdf")):
            order.action_issue_offer_pdf()
        self.assertFalse(order.issued_without_sales_acceptance)
        self.assertNotIn(
            "without Sales responsibility acceptance", order.issued_offer_audit,
        )

    def test_unaccepted_issue_notifies_assigned_sales_and_sales_manager_in_chatter(self):
        manager = self.env["res.users"].create({
            "name": "Lifecycle Sales Manager",
            "login": "lifecycle.sales.manager@example.test",
            "groups_id": [(6, 0, [
                self.env.ref("base.group_user").id,
                self.env.ref("sales_team.group_sale_manager").id,
            ])],
        })
        order = self._draft(user_id=self.salesperson.id)
        report_service = self.env["ir.actions.report"]
        with patch.object(
                type(report_service), "_render_qweb_pdf",
                return_value=(b"%PDF-test", "pdf")):
            order.action_issue_offer_pdf()
        exception_messages = order.message_ids.filtered(
            lambda message: "without Sales responsibility acceptance" in (message.body or "")
        )
        self.assertEqual(len(exception_messages), 1)
        recipients = exception_messages.partner_ids
        self.assertIn(order.user_id.partner_id, recipients)
        self.assertIn(manager.partner_id, recipients)

    def test_combined_order_view_has_one_visible_manual_item_number(self):
        base_view = self.env.ref("sale.view_order_form")
        arch = self.env["sale.order"].fields_view_get(
            view_id=base_view.id, view_type="form"
        )["arch"]
        root = etree.fromstring(arch.encode())
        item_fields = root.xpath(
            "//page[@name='order_lines']//field[@name='sn'][@string='Item #'][@optional='show']"
        )
        self.assertEqual(len(item_fields), 1)

    def test_named_custom_control_help_has_purpose_role_effect_and_next_action(self):
        cases = (
            (
                "Item #", "sale_revision_history.sale_order_item_number_once",
                "//attribute[@name='help']",
                ("item reference", "quotation specialist", "never generated", "before saving"),
            ),
            (
                "Purchase Price Estimate", "sale_order_product_pricing.sale_order_role_guidance",
                "//xpath[contains(@expr, 'purchase_price_estimate')]/attribute[@name='help']",
                ("expected supplier cost", "product pricing users", "used by product pricing", "before preview"),
            ),
            (
                "Price Origin", "sale_order_product_pricing.sale_order_product_pricing_form",
                "//field[@name='price_origin_label']",
                ("shows whether", "sales and quotation specialists", "sales manager certifies", "review it before"),
            ),
            (
                "Pricing Eligible", "sale_order_product_pricing.sale_order_role_guidance",
                "//xpath[contains(@expr, 'pricing_eligible')]/attribute[@name='help']",
                ("whether this line can be calculated", "product pricing users", "included in apply", "preview again"),
            ),
            (
                "Pricing Warning", "sale_order_product_pricing.sale_order_role_guidance",
                "//xpath[contains(@expr, 'pricing_warning')]/attribute[@name='help']",
                ("why a line will be skipped", "product pricing users", "prevents an unsafe apply", "preview again"),
            ),
            (
                "Preview", "sale_order_product_pricing.sale_order_product_pricing_form",
                "//button[@name='action_preview_product_pricing']",
                ("calculate and explain", "product pricing users", "without changing", "confirm apply"),
            ),
            (
                "Apply", "sale_order_product_pricing.sale_order_pricing_preview_form",
                "//button[@name='action_confirm_apply']",
                ("apply this reviewed proposal", "product pricing users", "updates only", "preview again"),
            ),
            (
                "Global Factor", "sale_order_product_pricing.sale_order_role_guidance",
                "//xpath[contains(@expr, 'global_factor')]/attribute[@name='help']",
                ("default multiplier", "product pricing users", "non-mutating result", "then apply"),
            ),
            (
                "Line Factor", "sale_order_product_pricing.sale_order_role_guidance",
                "//xpath[contains(@expr, 'line_factor')]/attribute[@name='help']",
                ("adjusts only", "product pricing users", "does not change", "preview is applied"),
            ),
            (
                "Free of Charge", "sale_order_product_pricing.sale_order_finance_controls_form",
                "//field[@name='is_free_of_charge']",
                ("zero-price exception", "pricing user or quotation/sales manager", "marks it", "before issue offer pdf"),
            ),
            (
                "Days of Expiry", "sale_order_product_pricing.sale_order_offer_expiry_form",
                "//field[@name='offer_expiry_days']",
                ("number of days", "sales and qs users", "expiration date", "before issuing"),
            ),
            (
                "VAT 14%", "sale_order_product_pricing.sale_order_finance_controls_form",
                "//field[@name='apply_vat'][@string='VAT 14%']",
                ("selected by default", "qs and sales users", "applied globally", "before issue offer pdf"),
            ),
            (
                "Retention", "sale_order_product_pricing.res_config_settings_finance_controls",
                "//field[@name='quotation_retention_tax_id']",
                ("withholding sales tax", "accounting managers", "reduces", "before sales uses"),
            ),
            (
                "Issue Offer PDF", "sale_revision_history.sale_order_view_form",
                "//button[@name='action_issue_offer_pdf']",
                ("customer offer pdf", "assigned sales or qs", "marks the offer sent", "create a revision"),
            ),
            (
                "Create Revision", "sale_revision_history.sale_order_view_form",
                "//button[@name='action_revision']",
                ("creates the next draft", "assigned sales or qs", "source remains locked", "mandatory reason"),
            ),
            (
                "Quotation requirements approval", "sale_order_product_pricing.sale_order_finance_controls_form",
                "//button[@name='action_approve_quotation_requirements']",
                ("eligible approver", "current exception", "server verifies", "requirement"),
            ),
        )
        for label, view_xmlid, xpath, required_fragments in cases:
            root = etree.fromstring(self.env.ref(view_xmlid).arch_db.encode())
            nodes = root.xpath(xpath)
            self.assertEqual(len(nodes), 1, "%s help target" % label)
            node = nodes[0]
            help_text = node.text if node.tag == "attribute" else node.get("help")
            normalized = " ".join((help_text or "").lower().split())
            for fragment in required_fragments:
                self.assertIn(fragment, normalized, "%s help missing %r" % (label, fragment))

    def test_history_action_is_limited_to_one_family_and_includes_current_draft(self):
        order = self._draft()
        order.with_context(_lifecycle_internal_token=_LIFECYCLE_INTERNAL_TOKEN).write({"state": "sent"})
        revision = self.env["sale.order"].browse(
            order.action_view_revision_wizard("First revision")["res_id"]
        )
        unrelated = self._draft()
        action = revision.action_open_revision_history()
        self.assertEqual(set(action["domain"][0][2]), {order.id, revision.id})
        self.assertNotIn(unrelated.id, action["domain"][0][2])
