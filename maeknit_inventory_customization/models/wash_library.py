from odoo import models, fields


class WashLibrary(models.Model):
    _name = 'wash.library'
    _description = 'Wash Library'
    _order = 'sequence, name'

    name = fields.Char(string='Wash Name', required=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(string='Sequence', default=10)

    _sql_constraints = [
        ('name_uniq', 'unique (name)', "Wash name already exists!"),
    ]
