{
    'name': 'Maeknit Email Customization',
    'description': 'Customize Email Templates',
    'summary': 'Custom Email Templates',
    'version': '1.0',
    'depends': ['mail', 'web'],
    'assets': {
                'web.assets_backend': [
                    'maeknit_email_customization/static/src/js/chatter_override.js',
                    'maeknit_email_customization/static/src/css/chatter_customization.css',
                    # 'your_module_name/static/src/components/chatter_override.xml', if needed
                ],
            },
    'author': 'Mahimul Islam (Maeknit)',
    'category': 'Tools',
    'description': """
        This module customizes the chatter functionality in Odoo.
    """,
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
    'website': 'https://maeknit.com',
}
