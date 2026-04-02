from odoo import models, fields


class RenderImageLine(models.Model):
    _inherit = 'render.image.line'

    bom_request_id = fields.Many2one(
        'maeknit.bom.request',
        string='BOM Request',
        ondelete='cascade',
        index=True,
    )
