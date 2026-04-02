from odoo import models, api, fields
import logging

class ServerActions(models.Model):
    _inherit = 'ir.actions.server'
    
    @api.model
    def _get_eval_context(self, action=None):
        """Override to add custom methods to the eval context."""
        eval_context = super(ServerActions, self)._get_eval_context(action=action)
        eval_context.update({
            'enforce_product_defaults': self.enforce_product_defaults,
        })
        return eval_context
    
    def enforce_product_defaults(self, products):
        """Enforce default values on newly created products."""
        ProductTemplate = self.env['product.template']
        
        for product in products:
            # Skip products that already have a product_category
            if hasattr(product, 'product_category') and product.product_category:
                continue
                
            logging.info(f"Enforcing defaults on product: {product.name}")
            
            # Set default product_category
            if not hasattr(product, 'product_category'):
                # This is a standard product without our custom field
                # We need to determine what category it should be based on other attributes
                if product.type == 'service':
                    product_category = 'services'
                else:
                    product_category = 'misc'
                
                # Use SQL to update the product directly since the field might not exist
                self.env.cr.execute("""
                    UPDATE product_template 
                    SET product_category = %s 
                    WHERE id = %s
                """, (product_category, product.id))
                
                logging.info(f"Added product_category {product_category} to product {product.name}")
                
                # Refresh the record to see the changes
                product.invalidate_cache()
                
        return True
