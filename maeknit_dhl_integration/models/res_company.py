# -*- coding: utf-8 -*-
from odoo import models, fields

class ResCompany(models.Model):
    _inherit = 'res.company'

    dhl_account_number = fields.Char(string="DHL Account Number")
    dhl_site_id = fields.Char(string="DHL SiteID")
    dhl_password = fields.Char(string="DHL Password")
    dhl_use_production = fields.Boolean(string="Use DHL Production Environment", default=False)
    dutify_api_key = fields.Char(string="Dutify API Key")
