from odoo import models, fields, api
import copy


class StructureLine(models.Model):
    _inherit = 'maeknit.structure.line'

    production_id = fields.Many2one('mrp.production', string='Manufacturing Order', ondelete='cascade')
    bom_request_id = fields.Many2one(required=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # If a line is created via MO and has no BOM Request yet,
            # inherit the MO's bom_request_id so the line is shared (single source of truth)
            if vals.get('production_id') and not vals.get('bom_request_id'):
                mo = self.env['mrp.production'].browse(vals['production_id'])
                if mo.bom_request_id:
                    vals['bom_request_id'] = mo.bom_request_id.id
        records = super().create(vals_list)
        for record in records:
            if record.production_id:
                record._sync_to_panel_cad('add')
        return records

    def write(self, vals):
        result = super().write(vals)
        if 'name' in vals:
            for record in self:
                if record.production_id:
                    record._sync_to_panel_cad('rename')
        return result

    def unlink(self):
        # Gather production + id pairs before deletion
        sync_info = [(r.production_id, r.id) for r in self if r.production_id]
        result = super().unlink()
        for production, line_id in sync_info:
            if production.exists():
                production._remove_structure_panel(f's_{line_id}')
        return result

    def _sync_to_panel_cad(self, action):
        """Add or rename a structure panel in the linked MO's measurement_widget_data."""
        mo = self.production_id
        if not mo:
            return
        data = copy.deepcopy(mo.measurement_widget_data or {})
        panel_key = f's_{self.id}'

        if action == 'add':
            if panel_key not in data:
                data[panel_key] = {
                    'name': self.name,
                    'measurements': [],
                    'image': None,
                    'image_attachment_id': None,
                    'image2': None,
                    'image2_attachment_id': None,
                }
            struct_panels = data.get('structurePanels', [])
            if not any(p['id'] == panel_key for p in struct_panels):
                struct_panels.append({'id': panel_key, 'name': self.name})
            data['structurePanels'] = struct_panels

        elif action == 'rename':
            if panel_key in data and isinstance(data[panel_key], dict):
                data[panel_key]['name'] = self.name
            struct_panels = data.get('structurePanels', [])
            for p in struct_panels:
                if p['id'] == panel_key:
                    p['name'] = self.name
            data['structurePanels'] = struct_panels

        mo.with_context(skip_bom_request_cad_sync=True).write({'measurement_widget_data': data})
