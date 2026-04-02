from odoo import models, fields, api, Command, _
import json

class CrmLeadQuoteConfirm(models.TransientModel):
    _name = 'crm.lead.quote.confirm'
    _description = 'CRM Lead Quote Confirmation'

    lead_id = fields.Many2one('crm.lead', string='Lead', required=True)
    warning_message = fields.Text(string='Warning Message', readonly=True)

    def action_confirm(self):
        """
        Confirm creating a quotation without any selected services
        """
        if not self.lead_id:
            return {'type': 'ir.actions.act_window_close'}
        
        # Create the default products
        created_products = self.lead_id._create_default_products()
        
        # Store created products for use in quotation lines
        if created_products:
            self.lead_id.x_created_products = json.dumps({
                'development': created_products.get('development', {}).id if created_products.get('development') else False,
                'garment': created_products.get('garment', {}).id if created_products.get('garment') else False,
                'swatch': created_products.get('swatch', {}).id if created_products.get('swatch') else False,
                'production': created_products.get('production', {}).id if created_products.get('production') else False,
                'grading': created_products.get('grading', {}).id if created_products.get('grading') else False,
                'reverse': created_products.get('reverse', {}).id if created_products.get('reverse') else False,
            })
        
        # Get the order lines we want to include
        order_lines = []
        
        # Add lines for newly created products
        created_product_lines = self.lead_id._get_created_product_lines()
        if created_product_lines:
            order_lines.extend([Command.create(line) for line in created_product_lines])
        
        # Call the parent's action_sale_quotations_new with bypass context
        action = self.lead_id.with_context(bypass_quote_check=True).action_sale_quotations_new()
        
        # Update the action's context to include our order lines
        if order_lines and 'context' in action:
            action['context'] = dict(action['context'])  # Make a copy to avoid modifying the original
            action['context']['default_order_line'] = order_lines
        
        # Close the wizard
        action['target'] = 'current'
        
        return action
        
    def action_cancel(self):
        """
        Cancel creating a quotation
        """
        return {'type': 'ir.actions.act_window_close'}
