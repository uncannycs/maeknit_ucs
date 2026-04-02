from odoo import models, api
import logging

class SyncCategories(models.TransientModel):
    _name = 'maeknit.sync.categories'
    _description = 'Sync Product Categories'

    @api.model
    def sync_all_products(self):
        """Sync all products to ensure product_category and categ_id are in sync"""
        # First ensure all required categories exist
        self.ensure_product_categories()
        
        products = self.env['product.template'].search([])
        updated_count = 0
        
        for product in products:
            # Get the expected categ_id based on product_category
            expected_categ_id = product._get_product_category_id(product.product_category)
            
            # If the categ_id doesn't match the expected value, update it
            if expected_categ_id and product.categ_id.id != expected_categ_id:
                # Use SQL to update directly to avoid triggering the write method
                self.env.cr.execute("""
                    UPDATE product_template 
                    SET categ_id = %s 
                    WHERE id = %s
                """, (expected_categ_id, product.id))
                updated_count += 1
                logging.info(f"Updated categ_id for product {product.name} (ID: {product.id})")
        
        logging.info(f"Sync complete: updated {updated_count} products")
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Sync Complete',
                'message': f'Updated {updated_count} products',
                'sticky': False,
                'type': 'success',
            }
        }
    
    @api.model
    def ensure_product_categories(self):
        """Ensure all required product categories exist"""
        ProductCategory = self.env['product.category']
        
        # Define the categories we need
        categories = [
            {'name': 'Yarn', 'xml_id': 'maeknit_inventory_customization.product_category_yarn'},
            {'name': 'Garment', 'xml_id': 'maeknit_inventory_customization.product_category_garment'},
            {'name': 'Swatch', 'xml_id': 'maeknit_inventory_customization.product_category_swatch'},
            {'name': 'Services', 'xml_id': 'maeknit_inventory_customization.product_category_services'},
            {'name': 'Misc', 'xml_id': 'maeknit_inventory_customization.product_category_misc'}
        ]
        
        for category_data in categories:
            # Check if category exists by XML ID
            category = self.env.ref(category_data['xml_id'], raise_if_not_found=False)
            
            if not category:
                # Check if category exists by name
                category = ProductCategory.search([('name', '=', category_data['name'])], limit=1)
                
                if not category:
                    # Create the category
                    category = ProductCategory.create({
                        'name': category_data['name']
                    })
                    logging.info(f"Created product category: {category_data['name']}")
                    
                    # Create XML ID for the category
                    self.env['ir.model.data'].create({
                        'name': category_data['xml_id'].split('.')[-1],
                        'module': 'maeknit_inventory_customization',
                        'model': 'product.category',
                        'res_id': category.id,
                    })
                    logging.info(f"Created XML ID {category_data['xml_id']} for category {category_data['name']}")
                else:
                    # Category exists but XML ID doesn't, create it
                    self.env['ir.model.data'].create({
                        'name': category_data['xml_id'].split('.')[-1],
                        'module': 'maeknit_inventory_customization',
                        'model': 'product.category',
                        'res_id': category.id,
                    })
                    logging.info(f"Created XML ID {category_data['xml_id']} for existing category {category_data['name']}")
        
        return True
    
    @api.model
    def view_product_categories(self):
        """Open the standard product categories view"""
        action = self.env.ref('product.product_category_action_form').read()[0]
        return action
