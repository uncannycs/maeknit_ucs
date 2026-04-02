from odoo import models, fields, api


class StructureLine(models.Model):
    """Structure lines for BOM Request"""
    _name = 'maeknit.structure.line'
    _description = 'MAEKNIK Structure Lines'
    _order = 'sequence, id'

    bom_request_id = fields.Many2one('maeknit.bom.request', string='BOM Request', required=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10)
    name = fields.Char(string='Name', required=True)
    description = fields.Text(string='Description')

    