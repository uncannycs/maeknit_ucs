from odoo import models, fields, api
import logging

class MrpBomLine(models.Model):
    _inherit = 'mrp.bom.line'
    
    structure_id = fields.Many2one(
        'maeknit.structure.line',
        string='Structure',
        store=True,
        help='Structure line from BOM Request'
    )