from odoo import models, fields, api


class RenderImageLine(models.Model):
    _name = 'render.image.line'
    _description = 'Render Image Line'
    _order = 'sequence, id'

    name = fields.Char(string='Image Name', default='Render Image')
    sequence = fields.Integer(string='Sequence', default=10)
    image = fields.Binary(string='Image', attachment=True)
    image_filename = fields.Char(string='Image Filename')

    # Relation to MRP Production (bom_request_id added by maeknit_sales_customization)
    production_id = fields.Many2one(
        'mrp.production',
        string='Manufacturing Order',
        ondelete='cascade',
        index=True
    )

    # For preview/zoom functionality
    image_url = fields.Char(string='Image URL', compute='_compute_image_url')

    @api.depends('image')
    def _compute_image_url(self):
        """Generate URL for image preview"""
        for record in self:
            if record.image:
                # Generate a URL that can be used for preview
                record.image_url = f'/web/image/{record._name}/{record.id}/image'
            else:
                record.image_url = False

    def action_preview_image(self):
        """Preview/zoom the image in a modal"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/image?model={self._name}&id={self.id}&field=image',
            'target': 'new',
        }

    def action_replace_image(self):
        """Open wizard to replace the image"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Replace Image',
            'res_model': 'render.image.line',
            'res_id': self.id,
            'view_mode': 'form',
            'view_id': self.env.ref('maeknit_mfg_customization.view_render_image_line_form').id,
            'target': 'new',
        }
