from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging

logging = logging.getLogger(__name__)


class ProductionReadyWizard(models.TransientModel):
    _name = 'production.ready.wizard'
    _description = 'Production Ready Wizard'

    source_bom_request_id = fields.Many2one(
        'maeknit.bom.request', 
        string='Source BOM Request', 
        required=True
    )
    
    product_tmpl_id = fields.Many2one(
        'product.template',
        string='Product Template',
        related='source_bom_request_id.product_tmpl_id',
        readonly=True
    )
    
    size_id = fields.Many2one(
        'product.attribute.value',
        string='Size',
        related='source_bom_request_id.size_id',
        readonly=True,
        help="Size is inherited from the source BOM Request"
    )
    
    colorway_id = fields.Many2one(
        'product.attribute.value',
        string='Original Colorway',
        related='source_bom_request_id.colorway_id',
        readonly=True,
        help="Original colorway from the development BOM"
    )
    
    available_colorway_ids = fields.Many2many(
        'product.attribute.value',
        compute='_compute_available_colorways',
        string='Available Colorways',
        help="Colorways filtered based on the product template"
    )
    
    selected_colorway_ids = fields.Many2many(
        'product.attribute.value',
        'production_wizard_colorway_rel',
        'wizard_id',
        'colorway_id',
        string='Select Colorways for Production',
        domain="[('id', 'in', available_colorway_ids)]",
        help="Select multiple colorways to create production BOMs"
    )
    
    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        related='source_bom_request_id.partner_id',
        readonly=True
    )
    
    rel_service = fields.Many2one(
        'product.product',
        string='Production Service',
        compute='_compute_production_service',
        store=True
    )
    
    @api.depends('product_tmpl_id')
    def _compute_available_colorways(self):
        """Compute available colorways from style.colorway table"""
        for wizard in self:
            if wizard.product_tmpl_id:
                style_colorways = self.env['style.colorway'].search([
                    ('product_tmpl_id', '=', wizard.product_tmpl_id.id),
                    ('active', '=', True)
                ])
                colorway_ids = style_colorways.mapped('colorway_id.id')
                
                if wizard.selected_colorway_ids:
                    colorway_ids = list(set(colorway_ids + wizard.selected_colorway_ids.ids))
                
                wizard.available_colorway_ids = [(6, 0, colorway_ids)]
            else:
                wizard.available_colorway_ids = [(6, 0, [])]

    @api.depends('source_bom_request_id')
    def _compute_production_service(self):
        """Find the Production Service product"""
        for wizard in self:
            production_service = self.env['product.product'].search([
                ('name', 'ilike', 'Production Service')
            ], limit=1)
            wizard.rel_service = production_service
    
    @api.onchange('colorway_id')
    def _onchange_colorway_id(self):
        """Pre-select the original colorway"""
        if self.colorway_id and not self.selected_colorway_ids:
            self.selected_colorway_ids = [(6, 0, [self.colorway_id.id])]

    def action_submit_request(self):
        """Create production BOMs and BOM Requests for selected colorways"""
        self.ensure_one()
        
        if not self.selected_colorway_ids:
            raise ValidationError(_("Please select at least one colorway."))
        
        if not self.rel_service:
            raise ValidationError(_("Production Service not found. Please create 'Production Service' product."))
        
        self._ensure_colorways_linked_to_template()
        
        source_bom_req = self.source_bom_request_id
        created_bom_requests = self.env['maeknit.bom.request']
        
        logging.info(f" Custom Code: logging Starting Production Ready: Creating BOMs for {len(self.selected_colorway_ids)} colorways")
        
        for colorway in self.selected_colorway_ids:
            logging.info(f" Custom Code: logging Processing colorway: {colorway.name}")
            
            new_bom = self._create_production_bom(
                source_bom_req,
                colorway
            )
            
            logging.info(f" Custom Code: logging Created BOM: {new_bom.display_name}")
            
            new_bom_request = self._create_bom_request(
                source_bom_req,
                new_bom,
                colorway
            )
            
            logging.info(f" Custom Code: logging Created BOM Request: {new_bom_request.name}")
            
            created_bom_requests |= new_bom_request
        
        return self.env.ref(
                    'maeknit_sales_customization.action_bom_request_production'
                ).read()[0]
    
    def _ensure_colorways_linked_to_template(self):
        """Ensure all selected colorways are linked to the product template via style.colorway"""
        for colorway in self.selected_colorway_ids:
            self.env['style.colorway'].get_or_create_style_colorway(
                self.product_tmpl_id.id,
                colorway.id
            )
            logging.info(f" Custom Code: logging Ensured colorway '{colorway.name}' is linked to template '{self.product_tmpl_id.name}'")
    
    
    def _ensure_attribute_lines(self, product_tmpl, size_attribute, colorway_attribute):
        """Ensure product template has size and colorway attribute lines"""
        # Check if size attribute line exists
        size_line = self.env['product.template.attribute.line'].search([
            ('product_tmpl_id', '=', product_tmpl.id),
            ('attribute_id', '=', size_attribute.id)
        ], limit=1)
        
        if not size_line:
            # Create size attribute line
            size_line = self.env['product.template.attribute.line'].create({
                'product_tmpl_id': product_tmpl.id,
                'attribute_id': size_attribute.id,
                'value_ids': [(4, self.size_id.id)]
            })
        
        # Check if colorway attribute line exists
        colorway_line = self.env['product.template.attribute.line'].search([
            ('product_tmpl_id', '=', product_tmpl.id),
            ('attribute_id', '=', colorway_attribute.id)
        ], limit=1)
        
        if not colorway_line:
            # Create colorway attribute line with all selected colorways
            colorway_line = self.env['product.template.attribute.line'].create({
                'product_tmpl_id': product_tmpl.id,
                'attribute_id': colorway_attribute.id,
                'value_ids': [(6, 0, self.selected_colorway_ids.ids)]
            })
    
    def _create_production_bom(self, source_bom_req, colorway):
        """Create a new production BOM based on source BOM (no duplicates)"""
        source_bom = source_bom_req.bom_id

        if not source_bom:
            raise ValidationError(_("Source BOM Request must have a linked BOM."))

        # Check existing production BOM
        existing_bom = self.env['mrp.bom'].search([
            ('product_tmpl_id', '=', self.product_tmpl_id.id),
            ('size_id', '=', self.size_id.id),
            ('colorway_id', '=', colorway.id),
            ('rel_service', '=', self.rel_service.id),
            ('gauge_id', '=', source_bom_req.gauge_id.id if source_bom_req.gauge_id else False),
        ], limit=1)

        if existing_bom:
            logging.info(f" Custom Code: logging Reusing existing Production BOM: {existing_bom.display_name}")
            return existing_bom

        # Create new Production BOM
        new_bom = self.env['mrp.bom'].create({
            'product_tmpl_id': self.product_tmpl_id.id,
            'product_qty': source_bom.product_qty,
            'product_uom_id': source_bom.product_uom_id.id,
            'type': source_bom.type,
            'rel_service': self.rel_service.id,
            'size_id': self.size_id.id,
            'colorway_id': colorway.id,
            'gauge_id': source_bom_req.gauge_id.id if source_bom_req.gauge_id else False,
        })

        for line in source_bom.bom_line_ids:
            self.env['mrp.bom.line'].create({
                'bom_id': new_bom.id,
                'product_id': line.product_id.id,
                'product_qty': line.product_qty,
                'product_uom_id': line.product_uom_id.id,
                'sequence': line.sequence,
            })

        logging.info(f" Custom Code: logging Created NEW Production BOM: {new_bom.display_name}")
        return new_bom
    
    def _create_bom_request(self, source_bom_req, new_bom, colorway):
        """Create Production BOM Request (no duplicates)"""

        existing_req = self.env['maeknit.bom.request'].search([
            ('product_tmpl_id', '=', self.product_tmpl_id.id),
            ('size_id', '=', self.size_id.id),
            ('colorway_id', '=', colorway.id),
            ('rel_service', '=', self.rel_service.id),
            ('is_production_bom', '=', True),
            ('gauge_id', '=', source_bom_req.gauge_id.id if source_bom_req.gauge_id else False),
        ], limit=1)

        if existing_req:
            logging.info(f" Custom Code: logging Production BOM Request already exists: {existing_req.name}")
            return existing_req

        # Create NEW request
        new_bom_req = self.env['maeknit.bom.request'].create({
            'partner_id': source_bom_req.partner_id.id,
            'product_tmpl_id': self.product_tmpl_id.id,
            'bom_id': new_bom.id,
            'rel_service': self.rel_service.id,
            'gauge_id': source_bom_req.gauge_id.id if source_bom_req.gauge_id else False,
            'type': source_bom_req.type,
            'colorway_id': colorway.id,
            'size_id': self.size_id.id,
            'state': 'draft',
            'sale_order_id': source_bom_req.sale_order_id.id if source_bom_req.sale_order_id else False,
            'is_production_bom': True,
            'rnd_task_template_id': False,
        })

        # Copy component lines
        for line in source_bom_req.bom_line_ids:
            self.env['maeknit.bom.request.line'].create({
                'bom_request_id': new_bom_req.id,
                'product_id': line.product_id.id,
                'product_qty': line.product_qty,
                'product_uom_id': line.product_uom_id.id,
                'sequence': line.sequence,
            })

        logging.info(f" Custom Code: logging Created NEW Production BOM Request: {new_bom_req.name}")
        return new_bom_req

    
    def action_cancel(self):
        """Close the wizard without doing anything"""
        return {'type': 'ir.actions.act_window_close'}
