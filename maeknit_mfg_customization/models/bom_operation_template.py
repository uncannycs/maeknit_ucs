from odoo import models, fields

class BOMOperationTemplate(models.Model):
    _name = 'maeknit.bom.operation.template'
    _description = 'BOM Operation Template'
    _table = 'maeknit_bom_operation_template'  # 👈 reuse old table

    name = fields.Char(string="Template Name", required=True)
    is_default = fields.Boolean(string="Is Default Template", default=False)
    line_ids = fields.One2many(
        'maeknit.bom.operation.template.line',
        'template_id',
        string='Operation Lines',
        copy=True,
    )
    related_service = fields.Selection(
        [('development', 'Development'), ('swatch', 'Swatch'),
         ('toile', 'Toile'), ('grading', 'Grading'), ('production', 'Production')],
        string='Service Type',
        required=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )


class BOMOperationTemplateLine(models.Model):
    _name = 'maeknit.bom.operation.template.line'
    _description = 'BOM Operation Template Line'
    _table = 'maeknit_bom_operation_template_line'  # 👈 reuse old table
    _order = 'sequence, id'

    template_id = fields.Many2one(
        'maeknit.bom.operation.template',
        string='Template',
        required=True,
        ondelete='cascade'
    )
    operation_id = fields.Many2one(
        'maeknit.shopfloor.operation',
        string='Operation',
        required=True
    )
    user_ids = fields.Many2many('hr.employee', string="Assignees")
    sequence = fields.Integer()
