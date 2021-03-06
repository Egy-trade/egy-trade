# -*- coding: utf-8 -*-
{
    'name': 'Egy-Trade',
    'description': 'Egy-Trade Technical Modifications',
    'version': '1.0.1',
    'author': 'EffVision',
    'category': 'Inventory',

    'depends': ['product', 'stock', 'purchase', 'purchase_stock', 'crm', 'sale_management', 'sale_margin'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/one_time.xml',
        'data/product.xml',
        'data/stock_picking.xml',
        'data/res_partner_documents.xml',
        'wizard/change_stage_wizard.xml',
        'wizard/set_stage_wizard.xml',
        'views/res_partner_view.xml',
        'reports/delivery_receipt.xml',
        'views/stock_view.xml',
        'views/stock_reports.xml',
        'views/stock_picking_view.xml',
        'views/purchase_view.xml',
        'views/product_view.xml',
        'views/sale_order.xml',
        'views/crm_lead.xml',
        'views/res_partner_document.xml',

    ],
    'application': True,
    'external_dependencies': {'python': ['pandas']}
}
