
{
    'name': 'OIT Contact Restriction',
    'summary': 'OIT Contact Restriction',
    'author': "OIT Solutions",
    'company': 'OIT Solutions',
    'website': "http://www.oit-solution.com",
    'version': '15.0.0.1.0',
    'category': "OIT Solutions/apps",
    'license': 'AGPL-3',
    'sequence': 1,
    'depends': [
        'base',
        'crm',
        'calendar',
        'sale',
    ],
    'data': [
        'security/security.xml',
        # 'report/',
        # 'wizard/',
        'views/res_users.xml',
        'views/res_partner.xml',
        'views/mail_activity.xml',
        'views/crm_lead.xml',
        'views/sale_order.xml',
        'views/calendar_event.xml',
        # 'data/',
    ],
    'demo': [
        # 'demo/',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}

