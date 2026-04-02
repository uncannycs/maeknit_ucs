from odoo import models, fields, api


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    fitting_notes_ids = fields.One2many(
        'maeknit.fitting.notes',
        'production_id',
        string='Fittings',
    )
    fitting_id = fields.Many2one(
        'maeknit.fitting.notes',
        compute='_compute_fitting_id',
        string='Fitting',
    )
    source_fitting_id = fields.Many2one(
        'maeknit.fitting.notes',
        string='Previous Fitting',
        readonly=True,
        copy=False,
    )

    @api.depends('fitting_notes_ids')
    def _compute_fitting_id(self):
        for rec in self:
            rec.fitting_id = rec.fitting_notes_ids[:1]

    def action_generate_fitting(self):
        self.ensure_one()
        # Block if fitting already exists — should not happen (button disappears)
        if self.fitting_id:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'maeknit.fitting.notes',
                'view_mode': 'form',
                'res_id': self.fitting_id.id,
                'target': 'current',
            }

        # Sample number is per product variant
        FittingNotes = self.env['maeknit.fitting.notes']
        existing_count = FittingNotes.search_count([('product_id', '=', self.product_id.id)])
        sample_number = f"Sample {existing_count + 1}"

        fitting = FittingNotes.create({
            'production_id': self.id,
            'sample_number': sample_number,
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'maeknit.fitting.notes',
            'view_mode': 'form',
            'res_id': fitting.id,
            'target': 'current',
        }

    def action_open_source_fitting(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'maeknit.fitting.notes',
            'view_mode': 'form',
            'res_id': self.source_fitting_id.id,
            'target': 'current',
        }
