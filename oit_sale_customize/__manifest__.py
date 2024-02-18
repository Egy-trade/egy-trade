
{
    'name': 'OIT Sale Customize',
    'summary': 'OIT Sale Customize',
    'author': "OIT Solutions",
    'company': 'OIT Solutions',
    'website': "http://www.oit-solution.com",
    'version': '13.0.0.1.0',
    'category': "OIT Solutions/apps",
    'license': 'AGPL-3',
    'sequence': 1,
    'depends': [
        'base',
        'sale',
        'sales_team',
        'crm',
        'sale_crm',
        'sale_management',
        'purchase',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/security.xml',
        # 'report/',
        'views/sale_order.xml',
        'views/terms_and_conditions.xml',
        'views/purchase_order.xml',
        'views/crm_lead.xml',
        'wizard/create_quotation_template.xml',
    ],
    'demo': [
        # 'demo/',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}

