# -*- coding: utf-8 -*-
{
    'name': 'Egy-Trade',
    'description': 'Egy-Trade Technical Modifications',
    'version': '0.0.1',
    'author': 'EffVision',
    'category': 'Inventory',

    'depends': ['product', 'stock', 'purchase', 'crm', 'sale'],
    'data': [
        'security/ir.model.access.csv',
        'data/one_time.xml',
        'data/product.xml',
        'data/stock_picking.xml',
        'wizard/change_stage_wizard.xml',
        'views/res_partner_view.xml',
        'views/stock_view.xml',
        'views/stock_picking_view.xml',
        # 'views/purchase_view.xml',
        'views/product_view.xml',

    ],
    'application': True,
    'external_dependencies': {'python': ['pandas']}
}
