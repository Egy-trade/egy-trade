# -*- coding: utf-8 -*-
{
    'name': "Attendance Modification Request ",
    'category': 'HR Attendance',
    'summary': "Attendance Modification Request ",
    'author': 'Usama Fathi',
    'depends': ['base', 'hr_attendance', 'mail'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/attendance_view.xml',
        'wizard/cancel_attendance_view.xml',
        'views/menu.xml',

    ],
    'application': True,
    'installable': True,
    'auto_install': False,
}
