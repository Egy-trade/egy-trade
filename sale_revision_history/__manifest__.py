# -*- encoding: utf-8 -*-
{
    "name": "Sale Revision History",
    "version": "16.0.2.1.0",
    "author": "PPTS [India] Pvt.Ltd.",
    "website": "http://www.pptssolutions.com",
    "sequence": 0,
    "depends": [
        "sale_order_product_pricing"
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
        'wizard/commercial_change.xml',
    ],
    # Revision History is part of the controlled pricing workflow.  Install it
    # automatically wherever that workflow is installed so the feature cannot
    # exist in source while silently disappearing from the database UI.
    "auto_install": True,
    "installable": True,
    "application": False,
    'images': ['static/description/banner.png'],

}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
