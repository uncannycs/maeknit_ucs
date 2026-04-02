from odoo import models, fields

class RnDTaskTemplate(models.Model):
    _name = 'maeknit.rnd.task.template'
    _description = 'R&D Task Template'

    name = fields.Char(string="Template Name", required=True)
    is_default = fields.Boolean(string="Is Default Template", default=False)
    related_service = fields.Selection(
        [('development', 'Development'), ('swatch', 'Swatch'), ('reverse', 'Reverse Engineering'),
         ('grading', 'Grading'), ('production', 'Production')],
        string='Service Type',
        required=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    line_ids = fields.One2many(
        'maeknit.rnd.task.template.line',
        'template_id',
        string='Task Lines',
        copy=True,
    )


class RnDTaskTemplateLine(models.Model):
    _name = 'maeknit.rnd.task.template.line'
    _description = 'R&D Task Template Line'
    _order = 'sequence, id'

    template_id = fields.Many2one(
        'maeknit.rnd.task.template',
        string='Template',
        required=True,
        ondelete='cascade'
    )
    name = fields.Char(string="Task Name", required=True)
    user_ids = fields.Many2many('res.users', string="Assignees")
    sequence = fields.Integer(default=10)
