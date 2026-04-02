from odoo import models, api, _
from markupsafe import Markup, escape
import logging
import re

class MailThread(models.AbstractModel):
    _inherit = 'mail.thread'

    def _apply_font_styling(self, body):
        """Apply consistent sans-serif styling and preserve line breaks properly."""
        if not body:
            return body

        body_str = str(body) if isinstance(body, Markup) else body

        # Normalize raw text or hybrid body (HTML fragments without <p> or <div>)
        is_html = bool(re.search(r'<(p|div|br|span|table|ul|ol|li|strong|em|a|b|i)\b', body_str, re.I))

        if not is_html:
            # Treat as plain text — escape HTML then preserve newlines as <br>
            safe = escape(body_str)
            safe = safe.replace("\r\n", "\n").replace("\n", "<br/>")
            styled = (
                '<div style="font-family: sans-serif; font-size: 13px; '
                'line-height: 1.5; white-space: normal;">'
                f'{safe}</div>'
            )
            return Markup(styled)

        # Handle HTML that may contain <br> tags but no top-level wrapper
        if not re.search(r'<(html|body|p|div)\b', body_str, re.I):
            body_str = f'<div>{body_str}</div>'

        # Inject font styling only if not already present
        if 'font-family: sans-serif' not in body_str:
            body_str = re.sub(
                r'<(div|p)([^>]*)>',
                r'<\1\2 style="font-family: sans-serif; font-size: 13px; line-height: 1.5;">',
                body_str,
                count=1,
            )

        return Markup(body_str)

    @api.returns('mail.message', lambda value: value.id)
    def message_post(self, **kwargs):
        """ Override the message_post method to apply sans-serif font styling and maintain threading. """
        # Log all kwargs for debugging
        
        # Log subject specifically
        
        # If no subject is provided, try to get the most recent subject from the thread
        if not kwargs.get('subject') and hasattr(self, '_name') and hasattr(self, 'id'):
            recent_message = self.env['mail.message'].search([
                ('model', '=', self._name),
                ('res_id', '=', self.id),
                ('subject', '!=', False),
            ], order='id desc', limit=1)
            
            if recent_message and recent_message.subject:
                kwargs['subject'] = recent_message.subject
                logging.info("Using most recent subject for continuity: %s", kwargs['subject'])
        
        # Apply sans-serif font styling to the body
        body = kwargs.get('body', '')
        if body:
            kwargs['body'] = self._apply_font_styling(body)
        
        message = super(MailThread, self).message_post(**kwargs)
        logging.info("Message posted with ID: %s, subject: %s", message.id, message.subject)
        
        return message
