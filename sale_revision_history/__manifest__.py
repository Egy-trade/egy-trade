# -*- encoding: utf-8 -*-
{
    "name": "Sale Revision History",
    "version": "12.0",
    "author": "PPTS [India] Pvt.Ltd.",
    "website": "http://www.pptssolutions.com",
    "sequence": 0,
    "depends": [
        "base",
        "sale",
        "sale_management"
    ],
    "category": "Sales,Invoicing",
    "complexity": "easy",
    'license': 'LGPL-3',
    'support': 'business@pptservices.com',
    "description": """
Quotation sale revision history
	""",
    "data": [
        'security/ir.model.access.csv',
        'views/sale_order_views.xml',
        'wizard/revision_reason.xml',
    ],
    "auto_install": False,
    "installable": True,
    "application": False,
    'images': ['static/description/banner.png'],

}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: