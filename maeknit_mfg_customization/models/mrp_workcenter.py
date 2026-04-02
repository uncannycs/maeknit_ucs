from odoo import models, fields, api
import logging


class MrpWorkcenter(models.Model):
    _inherit = 'mrp.workcenter'
    
    gauge_ids = fields.Many2many(
        'gauge.library',
        string='Gauges',
        help='Gauges supported by this workcenter (e.g., 7gg, 12gg). Used to automatically filter and select workcenters based on production requirements.'
    )
