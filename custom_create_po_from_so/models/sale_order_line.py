from odoo import models, fields, api
from odoo.exceptions import UserError
from odoo.tools import float_compare
from odoo.tools.misc import get_lang
from dateutil.relativedelta import relativedelta


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _purchase_service_prepare_line_values(self, purchase_order, quantity=False):
        """ Returns the values to create the purchase order line from the current SO line.
            :param purchase_order: record of purchase.order
            :rtype: dict
            :param quantity: the quantity to force on the PO line, expressed in SO line UoM
        """
        self.ensure_one()
        # compute quantity from SO line UoM
        product_quantity = self.product_uom_qty
        if quantity:
            product_quantity = quantity

        purchase_qty_uom = self.product_uom._compute_quantity(product_quantity, self.product_id.uom_po_id)

        # determine vendor (real supplier, sharing the same partner as the one from the PO, but with more accurate informations like validity, quantity, ...)
        # Note: one partner can have multiple supplier info for the same product
        supplierinfo = self.product_id._select_seller(
            partner_id=purchase_order.partner_id,
            quantity=purchase_qty_uom,
            date=purchase_order.date_order and purchase_order.date_order.date(),  # and purchase_order.date_order[:10],
            uom_id=self.product_id.uom_po_id
        )
        supplier_taxes = self.product_id.supplier_taxes_id.filtered(lambda t: t.company_id.id == self.company_id.id)
        taxes = purchase_order.fiscal_position_id.map_tax(supplier_taxes)

        # compute unit price
        price_unit = 0.0
        product_ctx = {
            'lang': get_lang(self.env, purchase_order.partner_id.lang).code,
            'company_id': purchase_order.company_id,
        }
        if supplierinfo:
            price_unit = self.env['account.tax'].sudo()._fix_tax_included_price_company(
                supplierinfo.price, supplier_taxes, taxes, self.company_id)
            if purchase_order.currency_id and supplierinfo.currency_id != purchase_order.currency_id:
                price_unit = supplierinfo.currency_id._convert(price_unit, purchase_order.currency_id,
                                                               purchase_order.company_id,
                                                               fields.Date.context_today(self))
            product_ctx.update({'seller_id': supplierinfo.id})
        else:
            product_ctx.update({'partner_id': purchase_order.partner_id.id})

        product = self.product_id.with_context(**product_ctx)
        name = product.display_name
        if product.description_purchase:
            name += '\n' + product.description_purchase

        return {
            'name': self.name,
            'product_qty': purchase_qty_uom,
            'product_id': self.product_id.id,
            'product_uom': self.product_id.uom_po_id.id,
            'price_unit': price_unit,
            'date_planned': fields.Date.from_string(purchase_order.date_order) + relativedelta(
                days=int(supplierinfo.delay)),
            'taxes_id': [(6, 0, taxes.ids)],
            'order_id': purchase_order.id,
            'sale_line_id': self.id,
        }

    def _purchase_service_generation(self):
        """ Create a Purchase for the first time from the sale line. If the SO line already created a PO, it
            will not create a second one.
        """
        sale_line_purchase_map = {}
        for line in self:
            # Do not regenerate PO line if the SO line has already created one in the past (SO cancel/reconfirmation case)
            # if line.product_id.service_to_purchase:
            result = line._purchase_service_create()
            sale_line_purchase_map.update(result)
        return sale_line_purchase_map

    def _purchase_service_create(self, quantity=False):
        """ On Sales Order confirmation, some lines (services ones) can create a purchase order line and maybe a purchase order.
            If a line should create a RFQ, it will check for existing PO. If no one is find, the SO line will create one, then adds
            a new PO line. The created purchase order line will be linked to the SO line.
            :param quantity: the quantity to force on the PO line, expressed in SO line UoM
        """
        PurchaseOrder = self.env['purchase.order']
        supplier_po_map = {}
        sale_line_purchase_map = {}
        for line in self:
            line = line.with_company(line.company_id)
            # determine vendor of the order (take the first matching company and product)
            suppliers = line.product_id._select_seller(quantity=line.product_uom_qty, uom_id=line.product_uom)
            if not suppliers:
                raise UserError(
                    _("There is no vendor associated to the product %s. Please define a vendor for this product.") % (
                    line.product_id.display_name,))
            supplierinfo = suppliers[0]
            partner_supplier = supplierinfo.partner_id

            # determine (or create) PO
            # purchase_order = supplier_po_map.get(partner_supplier.id)
            purchase_order=False
            print('purchase_order1',purchase_order)
            # if not purchase_order:
            #     purchase_order = PurchaseOrder.search([
            #         ('partner_id', '=', partner_supplier.id),
            #         ('state', '=', 'draft'),
            #         ('company_id', '=', line.company_id.id),
            #     ], limit=1)
            # print('purchase_order2',purchase_order)
            purchase_order=False
            if not purchase_order:
                values = line._purchase_service_prepare_order_values(supplierinfo)
                print('values',values)
                purchase_order = PurchaseOrder.with_context(mail_create_nosubscribe=True).create(values)
                print('purchase_order3', purchase_order)


            else:  # update origin of existing PO
                so_name = line.order_id.name
                origins = []
                if purchase_order.origin:
                    origins = purchase_order.origin.split(', ') + origins
                if so_name not in origins:
                    origins += [so_name]
                    purchase_order.write({
                        'origin': ', '.join(origins)
                    })
            supplier_po_map[partner_supplier.id] = purchase_order

            # add a PO line to the PO
            values = line._purchase_service_prepare_line_values(purchase_order, quantity=quantity)
            purchase_line = line.env['purchase.order.line'].create(values)

            # link the generated purchase to the SO line
            sale_line_purchase_map.setdefault(line, line.env['purchase.order.line'])
            sale_line_purchase_map[line] |= purchase_line
        return sale_line_purchase_map
