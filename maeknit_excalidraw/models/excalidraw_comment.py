from odoo import fields, models


class ExcalidrawComment(models.Model):
    _name = 'maeknit.excalidraw.comment'
    _description = 'Excalidraw Canvas Comment'
    _order = 'create_date asc'

    res_model = fields.Char(
        string='Related Model', required=True, index=True,
        help='Technical model name, e.g. maeknit.bom.request',
    )
    res_id = fields.Integer(
        string='Related Record ID', required=True, index=True,
    )
    field_name = fields.Char(
        string='Excalidraw Field Name', required=True, index=True,
        help='The field holding the Excalidraw JSON, e.g. excalidraw_data',
    )
    user_id = fields.Many2one(
        'res.users', string='Author', required=True,
        default=lambda self: self.env.user, ondelete='cascade',
    )
    partner_id = fields.Many2one(
        'res.partner', string='Author Partner',
        related='user_id.partner_id', store=True, readonly=True,
    )
    x = fields.Float(string='Scene X', required=True)
    y = fields.Float(string='Scene Y', required=True)
    message = fields.Text(string='Message', required=True)
    is_resolved = fields.Boolean(string='Resolved', default=False)

    # Element anchor — keeps the pin attached to its element when moved/scaled
    element_id = fields.Char(string='Anchored Element ID', index=True)
    element_frac_x = fields.Float(string='Element Fraction X', default=0.0)
    element_frac_y = fields.Float(string='Element Fraction Y', default=0.0)
