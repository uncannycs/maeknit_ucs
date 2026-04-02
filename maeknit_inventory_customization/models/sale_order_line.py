from odoo import models, api, fields
import logging

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'
    
    # Use a different method name to avoid conflicts
    @api.onchange('product_id')
    def _onchange_product_id_maeknit(self):
        """Apply our custom logic when product changes without calling super."""
        if self.product_id and self.product_id.product_tmpl_id:
            product_tmpl = self.product_id.product_tmpl_id
            
            # Check if product_category is set
            if not hasattr(product_tmpl, 'product_category') or not product_tmpl.product_category:
                # Determine appropriate category
                if product_tmpl.type == 'service':
                    product_category = 'services'
                else:
                    product_category = 'garment'
                
                # Use SQL to update directly
                self.env.cr.execute("""
                    UPDATE product_template 
                    SET product_category = %s 
                    WHERE id = %s
                """, (product_category, product_tmpl.id))
                
                logging.info(f"Set product_category to {product_category} for product {product_tmpl.name} from sale order")
                
                # Refresh the record
                product_tmpl.invalidate_cache()
