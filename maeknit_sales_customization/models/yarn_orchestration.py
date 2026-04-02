from odoo import models, fields, api

class YarnOrchestration(models.Model):
    _name = 'maeknit.yarn.orchestration'
    _description = 'Yarn Orchestration'

    bom_request_id = fields.Many2one(
        'maeknit.bom.request',
        string="BOM Request",
        required=True,
        ondelete='cascade'
    )
    name = fields.Char(string="Name", required=False)
    yarn_carrier = fields.Integer(string="Yarn Carrier", required=True)
    left_ply = fields.Integer(string="Left Ply", default=False)
    right_ply = fields.Integer(string="Right Ply", default=False)
