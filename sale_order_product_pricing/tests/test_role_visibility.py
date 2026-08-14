# -*- coding: utf-8 -*-

from lxml import etree

from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import SavepointCase

from ..models.sale_order import _PRICING_INTERNAL_TOKEN


class TestQuotationRoleVisibility(SavepointCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env.ref("base.res_partner_1")
        cls.product = cls.env["product.product"].create({
            "name": "Role Visibility Product", "sale_ok": True, "list_price": 100.0,
        })
        base_user = cls.env.ref("base.group_user")
        sales_user = cls.env.ref("sales_team.group_sale_salesman")
        sales_manager = cls.env.ref("sales_team.group_sale_manager")
        specialist_group = cls.env.ref("sale_order_product_pricing.quotation_specialist_group")
        designer_group = cls.env.ref("sale_order_product_pricing.lighting_designer_group")
        cls.specialist = cls.env["res.users"].create({
            "name": "Role test specialist", "login": "role.test.specialist@example.test",
            "groups_id": [(6, 0, [base_user.id, sales_user.id, specialist_group.id])],
        })
        cls.salesperson = cls.env["res.users"].create({
            "name": "Role test salesperson", "login": "role.test.sales@example.test",
            "groups_id": [(6, 0, [base_user.id, sales_user.id])],
        })
        cls.manager = cls.env["res.users"].create({
            "name": "Role test manager", "login": "role.test.manager@example.test",
            "groups_id": [(6, 0, [base_user.id, sales_manager.id])],
        })
        cls.designer = cls.env["res.users"].create({
            "name": "Role test designer", "login": "role.test.designer@example.test",
            "groups_id": [(6, 0, [base_user.id, designer_group.id])],
        })
        cls.employee = cls.env["res.users"].create({
            "name": "Role test employee", "login": "role.test.employee@example.test",
            "groups_id": [(6, 0, [base_user.id])],
        })

    def _order(self, owner=None):
        owner = owner or self.specialist
        order = self.env["sale.order"].create({
            "partner_id": self.partner.id, "user_id": owner.id,
            "quotation_specialist_id": self.specialist.id,
            "project": "Role visibility project",
        })
        # Every following commercial line/header mutation is made only after
        # the required Cairo-day Update Today decision has been recorded.
        if hasattr(order, "_record_commercial_change"):
            order._record_commercial_change("update_today")
        self.env["sale.order.line"].create({
            "order_id": order.id, "product_id": self.product.id,
            "name": self.product.display_name, "product_uom_qty": 1.0,
        })
        return order

    def test_specialist_assigns_only_active_internal_salesperson_and_audits(self):
        order = self._order()
        order.with_user(self.specialist).write({"user_id": self.salesperson.id})
        self.assertEqual(order.user_id, self.salesperson)
        self.assertTrue(self.env["sale.order.pricing.audit"].search([
            ("order_id", "=", order.id), ("reason", "ilike", "Salesperson assignment changed"),
        ]))
        self.salesperson.write({"active": False})
        with self.assertRaises(ValidationError):
            order.with_user(self.specialist).write({"user_id": self.salesperson.id})
        with self.assertRaises(ValidationError):
            order.with_user(self.specialist).write({"user_id": self.employee.id})

    def test_allowed_salesperson_compute_uses_candidate_permissions(self):
        order = self._order()
        allowed = order.with_user(self.specialist).allowed_salesperson_ids
        self.assertIn(self.salesperson, allowed)
        self.assertNotIn(self.employee, allowed)

    def test_salesperson_selector_uses_computed_allowed_users_domain(self):
        view = self.env.ref("sale_order_product_pricing.sale_order_role_assignment_form")
        root = etree.fromstring(view.arch_db.encode())
        node = root.xpath("//field[@name='user_id'][@position='attributes']")
        self.assertEqual(len(node), 1)
        domain = node[0].xpath("./attribute[@name='domain']/text()")
        self.assertEqual(domain, ["[('id', 'in', allowed_salesperson_ids)]"])
        self.assertNotIn("ref(", domain[0])

    def test_specialist_can_use_existing_contact_but_cannot_change_master_data(self):
        order = self._order()
        order.with_user(self.specialist).write({"partner_id": self.partner.id})
        with self.assertRaises(AccessError):
            self.partner.with_user(self.specialist).write({"name": "Forbidden contact edit"})
        with self.assertRaises(AccessError):
            self.env["res.partner"].with_user(self.specialist).create({"name": "Forbidden contact create"})

    def _require_standard_discount_policy(self):
        if "standard_discount_enabled" not in self.env.company._fields:
            self.skipTest("sale_discount_total is not installed in this module-only test database")

    def test_standard_discount_policy_enforces_enablement_origin_and_personal_cap(self):
        self._require_standard_discount_policy()
        order = self._order(owner=self.salesperson)
        line = order.order_line
        company = self.env.company
        company.write({"standard_discount_enabled": True, "standard_discount_maximum": 20.0,
                       "standard_discount_default_cap": 10.0})
        self.salesperson.write({"standard_discount_cap": 10.0})
        line.with_user(self.salesperson).write({"discount": 10.0})
        with self.assertRaises(ValidationError):
            line.with_user(self.salesperson).write({"discount": 10.01})
        company.write({"standard_discount_enabled": False})
        with self.assertRaises(AccessError):
            line.with_user(self.salesperson).write({"discount": 5.0})

    def test_standard_discount_create_and_import_cannot_bypass_policy(self):
        self._require_standard_discount_policy()
        order = self._order(owner=self.salesperson)
        company = self.env.company
        company.write({"standard_discount_enabled": True, "standard_discount_maximum": 20.0,
                       "standard_discount_default_cap": 10.0})
        self.salesperson.write({"standard_discount_cap": 10.0})
        values = {
            "order_id": order.id,
            "product_id": self.product.id,
            "name": self.product.display_name,
            "product_uom_qty": 1.0,
            "discount": 10.0,
        }
        line = self.env["sale.order.line"].with_user(self.salesperson).with_context(
            import_file=True,
        ).create(values)
        self.assertAlmostEqual(line.discount, 10.0)

        with self.assertRaises(ValidationError):
            self.env["sale.order.line"].with_user(self.salesperson).create(
                dict(values, discount=10.01)
            )
        company.write({"standard_discount_enabled": False})
        with self.assertRaises(AccessError):
            self.env["sale.order.line"].with_user(self.salesperson).create(
                dict(values, discount=5.0)
            )
        company.write({"standard_discount_enabled": True})
        with self.assertRaises(AccessError):
            self.env["sale.order.line"].with_user(self.salesperson).create({
                "order_id": order.id,
                "display_type": "line_note",
                "name": "Non-commercial note cannot be discounted",
                "discount": 5.0,
            })
        company.write({"standard_discount_enabled": True})
        line.sudo().with_context(_pricing_internal_token=_PRICING_INTERNAL_TOKEN).write({
            "price_origin": "product_pricing", "price_origin_verified": True,
            "price_origin_evidence": "product_pricing_apply",
        })
        with self.assertRaises(AccessError):
            line.with_user(self.salesperson).write({"discount": 5.0})

    def test_manager_discount_override_requires_reason_and_never_breaks_company_cap(self):
        self._require_standard_discount_policy()
        order = self._order(owner=self.manager)
        line = order.order_line
        self.env.company.write({"standard_discount_enabled": True, "standard_discount_maximum": 20.0,
                                "standard_discount_default_cap": 10.0})
        self.manager.write({"standard_discount_cap": 10.0})
        with self.assertRaises(ValidationError):
            line.with_user(self.manager).write({"discount": 15.0})
        order.with_user(self.manager).write({
            "standard_discount_override_reason": "Approved project-specific commercial concession.",
        })
        line.with_user(self.manager).write({"discount": 15.0})
        self.assertFalse(order.standard_discount_override_reason)
        self.assertTrue(line.standard_discount_override_used)
        # A manager's documented override is monitoring/audit evidence, not a
        # second quotation Finance approval gate.  Only QS-manager, VAT-off,
        # and configured high-value requirements may block Issue Offer PDF.
        self.assertNotIn("discount_override", order._finance_requirement_codes())
        self.assertTrue(self.env["sale.order.pricing.audit"].search([
            ("order_id", "=", order.id), ("reason", "ilike", "commercial concession"),
        ]))
        order.with_user(self.manager).write({"standard_discount_override_reason": "Attempt over hard cap"})
        with self.assertRaises(ValidationError):
            line.with_user(self.manager).write({"discount": 20.01})
        line.with_user(self.manager).write({"discount": 10.0})
        self.assertFalse(line.standard_discount_override_used)
        with self.assertRaises(AccessError):
            line.write({"standard_discount_override_used": True})

    def test_technical_scope_and_employee_directory_never_expose_commercial_records(self):
        order = self._order(owner=self.salesperson)
        order.with_user(self.manager).write({"lighting_designer_ids": [(4, self.designer.id)]})
        scope_model = self.env["quotation.technical.scope"].with_user(self.designer)
        scope = scope_model.search([("internal_reference", "=", order.name)])
        self.assertTrue(scope)
        self.assertEqual(set(scope_model.fields_get(["order_id", "designer_id"])), set())
        self.assertEqual(set(scope.line_ids.with_user(self.designer).fields_get(["sale_line_id"])), set())
        self.assertEqual(
            set(scope_model.fields_get([
                "client_organization", "owner_team_name", "latest_activity",
            ])),
            set(),
        )
        for view_xmlid, view_type in (
            ("sale_order_product_pricing.quotation_technical_scope_tree", "tree"),
            ("sale_order_product_pricing.quotation_technical_scope_form", "form"),
        ):
            view = scope_model.fields_view_get(
                view_id=self.env.ref(view_xmlid).id,
                view_type=view_type,
            )
            root = etree.fromstring(view["arch"].encode())
            forbidden = {
                "order_id", "designer_id", "sale_line_id",
                "client_organization", "owner_team_name", "latest_activity",
            }
            self.assertFalse(root.xpath(".//field[@name=%s]" % "'order_id'"))
            self.assertFalse({
                field.get("name") for field in root.xpath(".//field")
            }.intersection(forbidden))
            self.assertFalse(set(view["fields"]).intersection(forbidden))
        values = scope_model.search_read([], ["project_name", "internal_reference"])[0]
        self.assertEqual(set(values), {"id", "project_name", "internal_reference"})
        with self.assertRaises(AccessError):
            self.env["sale.order"].with_user(self.designer).check_access_rights("read", raise_exception=True)
        directory_model = self.env["quotation.project.directory"].with_user(self.employee)
        self.assertTrue(directory_model.search([("internal_reference", "=", order.name)]))
        self.assertEqual(set(directory_model.fields_get(["order_id"])), set())
        values = directory_model.search_read([], ["project_name", "internal_reference", "client_organization", "stage", "owner_team_name", "latest_activity"])[0]
        self.assertNotIn("order_id", values)
        self.assertNotIn("amount_total", values)

    def test_only_assigned_designer_reads_released_drawing(self):
        order = self._order(owner=self.salesperson)
        order.with_user(self.manager).write({"lighting_designer_ids": [(4, self.designer.id)]})
        drawing = self.env["quotation.technical.drawing"].with_user(self.manager).create({
            "order_id": order.id,
            "name": "Lighting layout",
            "file_name": "lighting-layout.pdf",
            "file_data": b"dGVzdA==",
        })
        visible = self.env["quotation.technical.drawing"].with_user(self.designer).search([
            ("id", "=", drawing.id),
        ])
        self.assertEqual(visible, drawing)
        self.assertEqual(
            set(visible.fields_get(["order_id", "name", "file_data"])),
            {"name", "file_data"},
        )
        drawing_model = self.env["quotation.technical.drawing"].with_user(self.designer)
        for view_xmlid, view_type in (
            ("sale_order_product_pricing.quotation_technical_drawing_tree", "tree"),
            ("sale_order_product_pricing.quotation_technical_drawing_form", "form"),
        ):
            view = drawing_model.fields_view_get(
                view_id=self.env.ref(view_xmlid).id,
                view_type=view_type,
            )
            root = etree.fromstring(view["arch"].encode())
            self.assertFalse(root.xpath(".//field[@name='order_id']"))
            self.assertNotIn("order_id", view["fields"])
        with self.assertRaises(AccessError):
            self.env["quotation.technical.drawing"].with_user(self.employee).check_access_rights(
                "read", raise_exception=True,
            )

    def test_specialist_has_no_purchase_access(self):
        if "purchase.order" not in self.env:
            self.skipTest("Purchase is tested when custom_create_po_from_so is installed")
        with self.assertRaises(AccessError):
            self.env["purchase.order"].with_user(self.specialist).check_access_rights(
                "read", raise_exception=True,
            )

    def test_view_only_read_does_not_create_role_projection(self):
        order = self._order(owner=self.salesperson)
        directory_model = self.env["quotation.project.directory"]
        directory_model.search([("order_id", "=", order.id)]).unlink()
        order.with_user(self.salesperson).read(["name", "state"])
        self.assertFalse(directory_model.search([("order_id", "=", order.id)]))
