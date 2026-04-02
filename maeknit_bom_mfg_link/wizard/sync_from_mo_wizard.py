import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MaeknitSyncFromMoWizard(models.TransientModel):
    _name = 'maeknit.sync.from.mo.wizard'
    _description = 'Sync Data to Development MO'

    target_mo_id = fields.Many2one(
        'mrp.production', string='Target Dev MO',
        required=True, readonly=True,
    )
    source_type = fields.Selection([
        ('swatch', 'Swatch'),
        ('toile', 'Toile'),
    ], string='Sync From', default='swatch', required=True)

    swatch_source_id = fields.Many2one(
        'mrp.production', string='Swatch MO',
        context={'show_product_name': True},
    )
    toile_source_id = fields.Many2one(
        'mrp.production', string='Toile MO',
        context={'show_product_name': True},
    )

    # Computed lists of what's available — used for domain in the view
    available_swatch_ids = fields.Many2many(
        'mrp.production',
        relation='sync_wiz_swatch_rel',
        column1='wizard_id', column2='mo_id',
        compute='_compute_available_ids',
        string='Available Swatches',
    )
    available_toile_ids = fields.Many2many(
        'mrp.production',
        relation='sync_wiz_toile_rel',
        column1='wizard_id', column2='mo_id',
        compute='_compute_available_ids',
        string='Available Toiles',
    )

    # Summary lines shown in the wizard for the selected source
    sync_preview = fields.Text(string='What will be synced', compute='_compute_sync_preview')

    @api.depends('target_mo_id', 'target_mo_id.partner_id')
    def _compute_available_ids(self):
        for rec in self:
            rec.available_swatch_ids = rec.target_mo_id.dev_swatch_mo_ids
            # Show ALL toile MOs for this client, not just linked ones
            if rec.target_mo_id.partner_id:
                rec.available_toile_ids = self.env['mrp.production'].search([
                    ('rel_service.name', '=', 'Toile Service'),
                    ('partner_id', '=', rec.target_mo_id.partner_id.id),
                ])
            else:
                rec.available_toile_ids = rec.target_mo_id.toile_mo_ids

    @api.onchange('source_type')
    def _onchange_source_type(self):
        self.swatch_source_id = False
        self.toile_source_id  = False

    @api.depends('source_type', 'swatch_source_id', 'toile_source_id')
    def _compute_sync_preview(self):
        for rec in self:
            src = rec.swatch_source_id if rec.source_type == 'swatch' else rec.toile_source_id
            if not src:
                rec.sync_preview = 'Select a source MO above to preview.'
                continue
            lines = []
            lines.append(f"Source: {src.name}  ({src.product_id.name or '—'})")
            lines.append('')
            checks = [
                ('Structure lines',         bool(src.structure_ids)),
                ('Structure CAD',           bool(src.structure_cad_data)),
                ('Artwork',                 bool(src.artwork_data_standalone or src.artwork_data)),
                ('Sketch',                  bool(src.excalidraw_data_standalone or src.excalidraw_data)),
                ('Development (Whole CAD)', bool(src.whole_cad_data)),
                ('Development (Garment)',   bool(src.garment_construction_data_standalone or src.garment_construction_data)),
                ('Stitch Density',          bool(src.calibration_data)),
                ('Components',              bool(src.move_raw_ids.filtered(lambda m: not m.scrap_id))),
            ]
            for label, has_data in checks:
                icon = '✓' if has_data else '○'
                lines.append(f'  {icon}  {label}')
            rec.sync_preview = '\n'.join(lines)

    def action_sync(self):
        self.ensure_one()
        src = self.swatch_source_id if self.source_type == 'swatch' else self.toile_source_id
        if not src:
            raise UserError(_('Please select a source MO to sync from.'))
        results = self.target_mo_id._sync_from_mo(src)
        ok  = sum(1 for v in results.values() if v.startswith('OK'))
        total = len(results)
        _logger.info(
            '[SYNC WIZARD] %s ← %s  %d/%d fields synced',
            self.target_mo_id.name, src.name, ok, total,
        )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Sync complete',
                'message': f'Synced {ok}/{total} data areas from {src.name}.',
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
