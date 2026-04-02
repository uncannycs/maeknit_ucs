from odoo import http
from odoo.http import request

class BOMRequestController(http.Controller):
    
    @http.route('/odoo/bom-request/<path:subpath>', type='http', auth='user')
    def bom_request_router(self, subpath, **kwargs):
        """
        Catch-all router for clean URLs like:
        /odoo/bom-request
        /odoo/bom-request/542
        /odoo/bom-request/development
        """
        env = request.env
        try:
            # CASE 1: numeric -> open record form
            if subpath.isdigit():
                action = env.ref('maeknit_sales_customization.action_bom_request')
                return request.redirect(
                    f"/web#action={action.id}&model=maeknit.bom.request&view_type=form&id={subpath}"
                )

            # CASE 2: known filter names
            if subpath.lower() == "development":
                action = env.ref('maeknit_sales_customization.action_bom_request_garment')
                return request.redirect(f"/web#action={action.id}&view_type=list")

            if subpath.lower() == "swatch":
                action = env.ref('maeknit_sales_customization.action_bom_request_swatch')
                return request.redirect(f"/web#action={action.id}&view_type=list")

            if subpath.lower() == "reverse":
                action = env.ref('maeknit_sales_customization.action_bom_request_reverse')
                return request.redirect(f"/web#action={action.id}&view_type=list")

            if subpath.lower() == "production":
                action = env.ref('maeknit_sales_customization.action_bom_request_production')
                return request.redirect(f"/web#action={action.id}&view_type=list")

            if subpath.lower() == "grading":
                action = env.ref('maeknit_sales_customization.action_bom_request_grading')
                return request.redirect(f"/web#action={action.id}&view_type=list")

            # Unknown path → default list
            action = env.ref('maeknit_sales_customization.action_bom_request')
            return request.redirect(f"/web#action={action.id}&view_type=list")
        except Exception:
            return request.redirect("/web#model=maeknit.bom.request&view_type=list")

    @http.route('/odoo/bom-request', type='http', auth='user')
    def bom_request_root(self, **kwargs):
        action = request.env.ref('maeknit_sales_customization.action_bom_request')
        return request.redirect(f"/web#action={action.id}&view_type=list")
