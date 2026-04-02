# custom_contact/__manifest__.py

{
    'name': 'Maeknit Contact Customization',
    'version': '1.0.0',
    'summary': 'Extends contact types to include Student, Brand, and Vendor',
    'description': 'This module enhances the contact model by introducing additional contact types '
                   'beyond Individual and Company, allowing better categorization of contacts.',
    'category': 'Contacts',
    'author': 'Mahimul Islam (Maeknit)',
    'website': 'https://maeknit.io',
    'depends': ['base', 'contacts'],
    'data': [
        'security/groups.xml',
        'views/res_partner_view_inherit.xml',
        'views/contacts_menu_override.xml',
    ],
    "assets": {
        "web.assets_backend": [
            "maeknit_contact_customization/static/src/scss/contact_type.scss",
        ],
    },
    'post_init_hook': 'set_default_contact_type',
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
