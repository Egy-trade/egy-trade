# -*- coding: utf-8 -*-

{
    'name': 'Merge Purchase Order',
    'category': 'Purchase',
    'summary': 'This module will merge purchase order.',
    'version': '15.0.1.0.0',
    'description': 'Merge Purchase Order',
    'license': "AGPL-3",

    'depends': [
        'purchase',
        'stock',
        'khalifa_customizations'
    ],
    'data': [
        'security/ir.model.access.csv',
        'wizard/merge_puchase_order_wizard_view.xml',
    ],
    'auto_install': False,
    'installable': True,
    'application': False

}
