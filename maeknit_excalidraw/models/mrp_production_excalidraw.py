from odoo import models


class MrpProductionExcalidraw(models.Model):
    _inherit = 'mrp.production'

    def write(self, vals):
        result = super().write(vals)
        for field_name in ('excalidraw_data', 'structure_cad_data'):
            if field_name in vals:
                for record in self:
                    self.env['bus.bus']._sendone(
                        f'excalidraw-{field_name}-mrp.production-{record.id}',
                        f'excalidraw_update_{field_name}',
                        {'uid': self.env.uid, 'resId': record.id, 'resModel': 'mrp.production'},
                    )
        return result
