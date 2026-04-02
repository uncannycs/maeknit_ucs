from odoo import models, fields

class ShopfloorOperation(models.Model):
    _name = "maeknit.shopfloor.operation"
    _description = "Shopfloor Operation"
    _order = "name"

    name = fields.Char(string="Operation Name", required=True)
    workcenter_tag_ids = fields.Many2many(
        "mrp.workcenter.tag",
        "shopfloor_operation_workcenter_tag_rel",
        "operation_id",
        "tag_id",
        string="Workcenter Tags"
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
