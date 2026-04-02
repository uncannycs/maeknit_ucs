from odoo import models, fields

class GaugeLibrary(models.Model):
    _name = 'gauge.library'
    _description = 'Gauge Library'

    name = fields.Char(string='Gauge Name', required=True)
    code = fields.Char(string='Gauge Code')
    description = fields.Text(string='Description')
    active = fields.Boolean(default=True)
    sequence = fields.Integer(string="Sequence", default=10)
    _order = "sequence, name"
    _sql_constraints = [
        ('name_uniq', 'unique (name)', "Gauge name already exists!"),
    ]