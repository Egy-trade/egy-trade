# -*- coding: utf-8 -*-
{
    'name': "product pricing in sale order",

    'summary': """
        product pricing in sale order
        """,

    'description': """
        Long description of module's purpose
    """,

    'author': "Abdullah/OIT-Solution",
    'website': "https://www.oit-solution.com",
    'category': 'Sales',
    'version': '16.0.2.2.2',

    # any module necessary for this one to work correctly
    'depends': ['base', 'sale', 'sale_management', 'egy-trade_custom', 'universal_discount', 'sale_stock'],

    # always loaded
    'data': [
        'security/res_groups.xml',
        'security/ir.model.access.csv',
        'views/product_pricing_preview.xml',
        'views/sale_order.xml',
        'views/offer_expiry.xml',
        'views/product_analysis.xml',
    ],

}
