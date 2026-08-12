# -*- coding: utf-8 -*-

from unittest.mock import patch

from lxml import etree

from odoo.exceptions import UserError
from odoo.tests.common import SavepointCase

from ..models.sale_order import _LIFECYCLE_INTERNAL_TOKEN


class QuotationLifecycleCase(SavepointCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env.ref("base.res_partner_1")
        cls.product = cls.env["product.product"].create({
            "name": "Lifecycle product", "sale_ok": True, "list_price": 100.0,
        })
        cls.salesperson = cls.env["res.users"].create({
            "name": "Lifecycle Salesperson",
            "login": "lifecycle.salesperson@example.test",
            "email": "lifecycle.salesperson@example.test",
            "groups_id": [(6, 0, [
                cls.env.ref("base.group_user").id,
                cls.env.ref("sales_team.group_sale_salesman").id,
            ])],
        })

    def _draft(self, **extra):
        values = {
            "partner_id": self.partner.id,
            "user_id": self.salesperson.id,
            "global_factor": 1.40,
            # Lifecycle tests exercise issue/locking, not Standard-tax policy.
            # CIF keeps the integrated finance gate deterministic without
            # relying on company-specific VAT/retention fixture records.
            "tax_treatment": "cif_no_taxes",
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

    def _update_today(self, order):
        wizard = self.env["quotation.commercial.change"].create({
            "sale_id": order.id, "decision": "update_today",
        })
        wizard.action_confirm()

    def test_manual_item_number_is_not_computed_or_copied_by_add_below(self):
        order = self._draft()
        source = order.order_line
        initial_line_ids = order.order_line.ids
        decision_action = source.action_add_below()
        self.assertEqual(decision_action["res_model"], "quotation.commercial.change")
        self.assertEqual(decision_action["target"], "new")
        self.assertEqual(order.order_line.ids, initial_line_ids)

        self._update_today(order)
        action = source.action_add_below()
        added = self.env["sale.order.line"].browse(action["context"]["focus_line_id"])
        self.assertEqual(source.sn, "A-01")
        self.assertFalse(added.product_id)
        self.assertEqual(added.name, "New product line")
        self.assertEqual(added.product_uom_qty, 0.0)
        self.assertFalse(added.sn)
        self.assertEqual(added.price_unit, 0.0)
        self.assertEqual(added.purchase_price_estimate, 0.0)
        self.assertEqual(added.discount, 0.0)
        self.assertEqual(added.factor, order.global_factor)
        self.assertEqual(added.line_factor, 1.0)
        self.assertEqual(added.sequence, source.sequence + 1)

    def test_daily_gate_update_today_keeps_date_order_and_audits(self):
        order = self._draft()
        original_date_order = order.date_order
        original_note = order.note
        # The HTTP/RPC request transaction rolls a rejected write back. Mirror
        # that boundary explicitly because this direct ORM test catches the
        # exception inside the surrounding SavepointCase transaction.
        with self.assertRaises(UserError), self.env.cr.savepoint():
            order.write({"note": "Commercial change without a decision"})
        order.invalidate_cache(fnames=["note"])
        self.assertEqual(order.note, original_note)
        self._update_today(order)
        order.write({"note": "Commercial change after Update Today"})
        self.assertEqual(order.date_order, original_date_order)
        self.assertEqual(order.commercial_change_decision, "update_today")
        self.assertEqual(order.commercial_change_decision_by, self.env.user)
        self.assertIn("Update Today", order.commercial_change_audit)
        self.assertEqual(
            order.validity_date - order.offer_date,
            __import__("datetime").timedelta(days=order.offer_expiry_days),
        )

    def test_direct_line_orm_create_write_unlink_require_daily_decision_and_lock_sent(self):
        order = self._draft()
        source = order.order_line
        line_model = self.env["sale.order.line"].with_context(import_file=True)
        with self.assertRaises(UserError):
            line_model.create({
                "order_id": order.id,
                "product_id": self.product.id,
                "name": "Imported product line",
            })
        with self.assertRaises(UserError):
            source.with_context(import_file=True).write({"name": "RPC change"})
        with self.assertRaises(UserError):
            source.with_context(import_file=True).unlink()

        self._update_today(order)
        added = line_model.create({
            "order_id": order.id,
            "product_id": self.product.id,
            "name": "Imported product line",
        })
        source.with_context(import_file=True).write({"name": "Approved RPC change"})
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

    def test_initial_nested_create_and_finance_tax_write_need_no_daily_decision(self):
        order = self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "tax_treatment": "cif_no_taxes",
            "order_line": [(0, 0, {
                "product_id": self.product.id,
                "name": self.product.display_name,
                "product_uom_qty": 1.0,
            })],
        })
        self.assertFalse(order.commercial_change_date)
        self.assertFalse(order.order_line.tax_id)

    def test_create_revision_archives_draft_and_opens_successor(self):
        order = self._draft()
        wizard = self.env["quotation.commercial.change"].create({
            "sale_id": order.id,
            "decision": "create_revision",
            "reason": "Customer requested a revised commercial option.",
        })
        action = wizard.action_confirm()
        revision = self.env["sale.order"].browse(action["res_id"])
        self.assertFalse(order.active)
        self.assertEqual(order.current_revision_id, revision)
        self.assertEqual(revision.state, "draft")
        self.assertEqual(revision.revision_number, 1)
        self.assertEqual(revision.commercial_change_decision, "create_revision")
        self.assertIn(order.name, revision.name)

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
        with self.assertRaises(UserError):
            order.write({"note": "RPC mutation"})
        with self.assertRaises(UserError):
            order.order_line.write({"name": "Import mutation"})
        with self.assertRaises(UserError):
            order.action_quotation_send()

    def test_confirmation_allows_only_issued_sent_to_sale_transition(self):
        order = self._draft()
        report_service = self.env["ir.actions.report"]
        with patch.object(
                type(report_service), "_render_qweb_pdf",
                return_value=(b"%PDF-test", "pdf")):
            order.action_issue_offer_pdf()
        with self.assertRaises(UserError):
            order.write({"state": "sale"})
        order.action_confirm()
        self.assertEqual(order.state, "sale")

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
                ("adjusts only", "product pricing users", "does not change", "before applying"),
            ),
            (
                "Free of Charge", "sale_order_product_pricing.sale_order_finance_controls_form",
                "//field[@name='is_free_of_charge']",
                ("zero-price exception", "pricing user or quotation/sales manager", "marks it", "before issue offer pdf"),
            ),
            (
                "Days of Expiry", "sale_order_product_pricing.sale_order_offer_expiry_form",
                "//field[@name='offer_expiry_days']",
                ("number of days", "quotation, sales, or accounting managers", "changes the offer validity", "before saving"),
            ),
            (
                "Tax Treatment", "sale_order_product_pricing.sale_order_finance_controls_form",
                "//field[@name='tax_treatment']",
                ("tax policy", "finance, quotation, sales, or accounting managers", "standard applies", "before adding or issuing"),
            ),
            (
                "Retention", "sale_order_product_pricing.res_config_settings_finance_controls",
                "//field[@name='quotation_retention_tax_id']",
                ("withholding tax", "finance or accounting managers", "deducts", "before using"),
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
                "Approval", "sale_order_product_pricing.sale_order_finance_controls_form",
                "//button[@name='action_approve_finance_requirements']",
                ("approves every current exception", "quotation or sales management", "invalidates it", "then issue"),
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
        revision = self.env["sale.order"].browse(
            self.env["quotation.commercial.change"].create({
                "sale_id": order.id,
                "decision": "create_revision",
                "reason": "First revision",
            }).action_confirm()["res_id"]
        )
        unrelated = self._draft()
        action = revision.action_open_revision_history()
        self.assertEqual(set(action["domain"][0][2]), {order.id, revision.id})
        self.assertNotIn(unrelated.id, action["domain"][0][2])
