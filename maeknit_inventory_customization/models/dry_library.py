from odoo import models, fields


class DryLibrary(models.Model):
    _name = 'dry.library'
    _description = 'Dry Library'
    _order = 'sequence, name'

    name = fields.Char(string='Dry Name', required=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(string='Sequence', default=10)

    _sql_constraints = [
        ('name_uniq', 'unique (name)', "Dry name already exists!"),
    ]
