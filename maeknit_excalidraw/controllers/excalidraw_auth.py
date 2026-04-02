from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)


class ExcalidrawAuthController(http.Controller):
    
    @http.route('/excalidraw/auth/callback', type='http', auth='user', website=True)
    def excalidraw_callback(self, **kwargs):
        """
        OAuth callback endpoint for Excalidraw authentication
        Receives the JWT token and stores it in the MO record
        """
        try:
            # Get the state parameter (MO ID)
            mo_id = kwargs.get('state')
            
            if not mo_id:
                return request.render('maeknit_mfg_customization.excalidraw_auth_error', {
                    'error': 'Missing state parameter'
                })
            
            # This will be handled by JavaScript on the frontend
            # The token comes in the URL hash fragment, not query params
            return request.render('maeknit_mfg_customization.excalidraw_auth_success', {
                'mo_id': mo_id
            })
            
        except Exception as e:
            _logger.error(f"Excalidraw OAuth callback error: {e}")
            return request.render('maeknit_mfg_customization.excalidraw_auth_error', {
                'error': str(e)
            })
    
    @http.route('/excalidraw/auth/save_token', type='json', auth='user')
    def save_token(self, mo_id, token):
        """
        Save the Excalidraw JWT token to the MO record
        """
        try:
            mo = request.env['mrp.production'].browse(int(mo_id))
            
            if not mo.exists():
                return {'success': False, 'error': 'Manufacturing Order not found'}
            
            mo.write({'excalidraw_user_token': token})
            
            return {'success': True, 'message': 'Token saved successfully'}
            
        except Exception as e:
            _logger.error(f"Error saving Excalidraw token: {e}")
            return {'success': False, 'error': str(e)}
