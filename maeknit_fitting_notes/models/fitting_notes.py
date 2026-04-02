from odoo import models, fields, api, _
from odoo.exceptions import UserError


class MaeknitFittingNotes(models.Model):
    _name = 'maeknit.fitting.notes'
    _description = 'Fitting'
    _rec_name = 'sample_number'

    production_id = fields.Many2one(
        'mrp.production',
        string='Manufacturing Order',
        required=True,
        ondelete='cascade',
        readonly=True,
    )
    product_id = fields.Many2one(
        'product.product',
        related='production_id.product_id',
        store=True,
        string='Product',
    )
    bom_id = fields.Many2one(
        'mrp.bom',
        related='production_id.bom_id',
        store=True,
        string='Bill of Materials',
    )
    company_id = fields.Many2one(
        'res.company',
        related='production_id.company_id',
        store=True,
        string='Company',
    )
    sample_number = fields.Char(string='Sample', readonly=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('sent_to_shop_floor', 'Sent to Shop Floor'),
    ], default='draft', string='State', required=True)

    next_production_id = fields.Many2one(
        'mrp.production',
        string='Next Manufacturing Order',
        readonly=True,
        copy=False,
    )

    # Tabs
    sketch_data = fields.Text(string='Sketch Data')   # Excalidraw JSON
    notes = fields.Text(string='Notes')

    @api.depends('product_id', 'sample_number')
    def _compute_display_name(self):
        for rec in self:
            product = rec.product_id.display_name or ''
            sample = rec.sample_number or ''
            rec.display_name = f"{product} – {sample}" if (product and sample) else (product or sample or 'Fitting')

    def action_open_production(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'mrp.production',
            'view_mode': 'form',
            'res_id': self.production_id.id,
            'target': 'current',
        }

    def action_confirm(self):
        self.ensure_one()
        self.state = 'confirmed'

    def action_set_draft(self):
        self.ensure_one()
        self.state = 'draft'

    def action_manufacture(self):
        self.ensure_one()
        if self.next_production_id:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'mrp.production',
                'view_mode': 'form',
                'res_id': self.next_production_id.id,
                'target': 'current',
            }

        original = self.production_id
        bom_request = original.bom_request_id

        # ── PATH 1: BOM Request exists ──────────────────────────────────────────
        # Use the same revision wizard flow as "New Sample" on BOM Request.
        # Bypass the UI by creating the wizard programmatically and calling
        # action_submit_request() directly with Measurement Change as default.
        if bom_request:
            eco_type = (
                self.env['mrp.eco.type'].search([('name', 'ilike', 'Measurement')], limit=1)
                or self.env['mrp.eco.type'].search([], limit=1)
            )
            if not eco_type:
                raise UserError(_("No ECO type configured. Please set up Engineering Change types first."))

            wizard = self.env['revision.request.wizard'].with_context(
                active_model='maeknit.bom.request',
                active_id=bom_request.id,
            ).create({
                'sale_order_line_id': bom_request.sale_order_line_id.id or False,
                'sale_order_id': bom_request.sale_order_id.id or False,
                'product_id': original.product_id.id,
                'change_type': eco_type.id,
                'description': f"Fitting – {self.sample_number or 'New Sample'}",
                'responsible': self.env.user.id,
            })

            result = wizard.action_submit_request()

            # Capture the new MFG and link it back to this fitting
            if result and result.get('res_model') == 'mrp.production' and result.get('res_id'):
                new_mo = self.env['mrp.production'].browse(result['res_id'])
                new_mo.source_fitting_id = self.id
                self.next_production_id = new_mo
                # action_generate_mo doesn't carry rel_service — copy it from original
                if original.rel_service:
                    new_mo.rel_service = original.rel_service

            self.state = 'sent_to_shop_floor'
            return result or {'type': 'ir.actions.act_window_close'}

        # ── PATH 2: No BOM Request — direct BOM + MFG copy ─────────────────────
        bom = original.bom_id
        new_version = (bom.version or 1) + 1
        new_bom = bom.copy({'version': new_version}) if bom else False

        # Force-write sample on new BOM — bom.copy() defers _compute_sample so
        # the stored column keeps "Sample 1" until recompute, cascading wrong
        # values into dependent records. Writing directly fixes the ordering.
        if new_bom:
            new_bom._write({'sample': f"Sample {new_version}"})
            new_bom.invalidate_recordset(['sample'])

        copy_defaults = {'source_fitting_id': self.id}
        if new_bom:
            copy_defaults['bom_id'] = new_bom.id

        new_mo = original.copy(copy_defaults)

        # Belt-and-suspenders: write sample directly in case related recompute
        # runs after copy and overwrites with the old chain value
        new_mo._write({'sample': f"Sample {new_version}"})
        new_mo.invalidate_recordset(['sample'])

        self.next_production_id = new_mo
        self.state = 'sent_to_shop_floor'

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'mrp.production',
            'view_mode': 'form',
            'res_id': new_mo.id,
            'target': 'current',
        }
