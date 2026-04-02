from odoo import models


class BomRequestExcalidraw(models.Model):
    _inherit = 'maeknit.bom.request'

    def write(self, vals):
        result = super().write(vals)
        if 'excalidraw_data' in vals:
            for record in self:
                self.env['bus.bus']._sendone(
                    f'excalidraw-excalidraw_data-maeknit.bom.request-{record.id}',
                    'excalidraw_update_excalidraw_data',
                    {'uid': self.env.uid, 'resId': record.id, 'resModel': 'maeknit.bom.request'},
                )
        if 'structure_cad_data' in vals:
            for record in self:
                self.env['bus.bus']._sendone(
                    f'structure-cad-maeknit.bom.request-{record.id}',
                    'structure_cad_update',
                    {'uid': self.env.uid, 'resId': record.id, 'resModel': 'maeknit.bom.request'},
                )
        return result
