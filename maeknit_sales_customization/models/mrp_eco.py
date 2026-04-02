import logging
from odoo import models, fields, api
from odoo.osv import expression

class MrpEco(models.Model):
    _inherit = 'mrp.eco'

    state = fields.Selection(selection_add=[
            ('draft', 'Draft'),
            ('progress', 'In Progress'),
            ('waiting', 'Waiting for Approval'),
            ('approved', 'Lab Approved'),
        ], ondelete={
            'draft': 'set default',
            'progress': 'set default',
            'waiting': 'set default', 
            'approved': 'set default',
        })
    
    bom_request_ids = fields.One2many('maeknit.bom.request', 'eco_id', string='Related BOM Requests')
    
    def write(self, vals):
        """Override write to sync ECO changes back to BOM Requests"""
        res = super(MrpEco, self).write(vals)
        
        if not self.env.context.get('skip_bom_request_sync') and ('state' in vals or 'stage_id' in vals):
            self._sync_state_with_bom_requests(vals)
        
        return res
    
    def _sync_state_with_bom_requests(self, vals):
        """Sync ECO state changes with related BOM Requests"""
        for eco in self:
            if not eco.bom_request_ids:
                continue

            bom_request_vals = {}

            # Map ECO states to BOM Request states
            if 'state' in vals:
                eco_to_bom_state = {
                    'draft': 'draft',
                    'progress': 'ready_to_program',
                    'progress': 'mo_confirmed',
                    'done': 'done',
                    'cancel': 'cancelled',
                }
                bom_state = eco_to_bom_state.get(vals['state'])
                if bom_state:
                    bom_request_vals['state'] = bom_state

            # Sync stage changes if stage_id updated
            if 'stage_id' in vals and vals['stage_id']:
                stage = self.env['mrp.eco.stage'].browse(vals['stage_id'])
                if stage:
                    bom_request_vals['stage_id'] = stage.id
                    bom_state = self._get_bom_state_from_stage(stage)
                    if bom_state:
                        bom_request_vals['state'] = bom_state

            if bom_request_vals:
                eco.bom_request_ids.sudo().with_context(skip_eco_sync=True).write(bom_request_vals)
                logging.info(
                    f"[ECO SYNC] Updated {len(eco.bom_request_ids)} BOM Requests from ECO {eco.name}: {bom_request_vals}"
                )

        return True

    def _get_bom_state_from_stage(self, stage):
        """Derive BOM Request state from ECO stage"""
        if not stage:
            return False

        stage_name = (stage.name or '').strip().lower()

        if 'draft' in stage_name:
            return 'draft'
        elif 'program' in stage_name or 'progress' in stage_name:
            return 'ready_to_program'
        elif 'review' in stage_name or 'confirm' in stage_name:
            return 'mo_confirmed'
        elif 'produce' in stage_name or 'quality' in stage_name:
            return 'produced'
        elif 'done' in stage_name or 'complete' in stage_name:
            return 'done'
        elif 'cancel' in stage_name:
            return 'cancelled'
        return 'draft'


    def action_new_revision(self):
        for eco in self:
            domain = [('res_model', '=', 'product.template'), ('res_id', '=', eco.product_tmpl_id.id)]
            if eco.type == 'bom':
                if eco.production_id:
                    # This ECO was generated from a MO. Uses it MO as base for the revision.
                    eco.new_bom_id = eco.production_id._create_revision_bom(eco.will_update_version)
                if not eco.new_bom_id:
                    eco.new_bom_id = eco.bom_id.sudo().copy(default={
                        'version': eco.will_update_version and eco.bom_id.version + 1 or eco.bom_id.version,
                        'active': False,
                        'previous_bom_id': eco.bom_id.id,
                    })
                if eco.bom_id.product_id:
                    domain = expression.OR([domain, ['&', ('res_model', '=', 'product.product'), ('res_id', 'in', eco.bom_id.product_id.ids)]])
                else:
                    domain = expression.OR([domain, ['&', ('res_model', '=', 'product.product'), ('res_id', 'in', self.env["product.product"].search([('product_tmpl_id', 'in', eco.product_tmpl_id.ids)]).ids)]])
                domain = expression.AND([domain, [('attached_on_mrp', '=', 'bom')]])
            else:
                domain = expression.OR([domain, ['&', ('res_model', '=', 'product.product'), ('res_id', 'in', self.env["product.product"].search([('product_tmpl_id', 'in', eco.product_tmpl_id.ids)]).ids)]])
            
            if eco.bom_id:
                bom_request_vals = {
                    'bom_id': eco.bom_id.id,
                    'product_id': eco.bom_id.product_id.id if eco.bom_id.product_id else eco.bom_id.product_tmpl_id.product_variant_ids[0].id,
                    'product_qty': eco.bom_id.product_qty,
                    'notes': f'BOM Request created from ECO revision {eco.name}',
                    'state': 'draft',
                    'eco_id': eco.id,  # Link to this ECO
                    'stage_id': eco.stage_id.id if eco.stage_id else False,
                }
                
                # Try to find a related sales order if available
                sale_order = self.env['sale.order'].search([
                    ('state', 'in', ['draft', 'sent', 'sale']),
                    ('order_line.product_id', '=', bom_request_vals['product_id'])
                ], limit=1)
                
                if sale_order:
                    bom_request_vals['sale_order_id'] = sale_order.id
                    # Find the specific order line
                    order_line = sale_order.order_line.filtered(
                        lambda l: l.product_id.id == bom_request_vals['product_id']
                    )
                    if order_line:
                        bom_request_vals['sale_order_line_id'] = order_line[0].id
                
                bom_request = self.env['maeknit.bom.request'].create(bom_request_vals)
                logging.info(f"Created BOM Request {bom_request.name} referencing BOM {eco.bom_id.id} from ECO {eco.name}")

            # Continue with existing revision logic
            if eco.bom_id and eco.type == 'bom':
                new_bom = eco.bom_id.copy()
                eco.new_bom_id = new_bom.id
                
                # Copy attachments from old BOM to new BOM
                attachments = self.env['ir.attachment'].search([
                    ('res_model', '=', 'mrp.bom'),
                    ('res_id', '=', eco.bom_id.id)
                ])
                
                for attachment in attachments:
                    attachment.copy({
                        'res_id': new_bom.id,
                        'name': f"Copy of {attachment.name}"
                    })
                
                logging.info(f"Created new BOM revision {new_bom.id} from ECO {eco.name}")

            docs = self.env['product.document'].search(domain)
            for doc in docs:
                doc.copy({'res_model': 'mrp.eco', 'res_id': eco.id, 'origin_attachment_id': doc.ir_attachment_id.id})
        self.write({'state': 'draft'})
