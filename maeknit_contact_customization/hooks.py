# custom_contact/hooks.py
from odoo import SUPERUSER_ID, api

def set_default_contact_type(env):
    partners = env['res.partner'].with_user(SUPERUSER_ID).search([('contact_type', '=', False)])
    for partner in partners:
        if partner.company_type == 'company':
            partner.contact_type = 'brand'  # default mapping
        else:
            partner.contact_type = 'individual'
