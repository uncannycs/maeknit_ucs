import logging
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

# Human-readable tab label for log notes
_FIELD_LABELS = {
    'excalidraw_data': 'Sketch',
    'structure_cad_data': 'Structure CAD',
    'garment_construction_data': 'Garment Construction',
}


class ExcalidrawCommentController(http.Controller):

    # ── User search (for @mentions) ───────────────────────────────────────────

    @http.route('/maeknit/excalidraw/users/search', type='json', auth='user')
    def search_users(self, q='', limit=8):
        """Return internal users matching q for @mention autocomplete."""
        users = request.env['res.users'].search([
            ('name', 'ilike', q),
            ('active', '=', True),
            ('share', '=', False),  # internal users only
        ], limit=int(limit), order='name asc')
        return {
            'users': [
                {'id': u.id, 'name': u.name, 'partner_id': u.partner_id.id}
                for u in users
            ]
        }

    # ── List ──────────────────────────────────────────────────────────────────

    @http.route('/maeknit/excalidraw/comments/list', type='json', auth='user')
    def list_comments(self, res_model, res_id, field_name):
        """Return all comments for a given (res_model, res_id, field_name)."""
        comments = request.env['maeknit.excalidraw.comment'].search([
            ('res_model', '=', res_model),
            ('res_id', '=', int(res_id)),
            ('field_name', '=', field_name),
        ])
        return {'comments': [self._fmt(c) for c in comments]}

    # ── Create ────────────────────────────────────────────────────────────────

    @http.route('/maeknit/excalidraw/comments/create', type='json', auth='user')
    def create_comment(self, res_model, res_id, field_name, x, y, message,
                       partner_ids=None, element_id=None, element_frac_x=0.0, element_frac_y=0.0):
        """Create a new comment pinned at scene coordinates (x, y), optionally anchored to an element."""
        vals = {
            'res_model': res_model,
            'res_id': int(res_id),
            'field_name': field_name,
            'x': float(x),
            'y': float(y),
            'message': message.strip(),
        }
        if element_id:
            vals['element_id'] = element_id
            vals['element_frac_x'] = float(element_frac_x)
            vals['element_frac_y'] = float(element_frac_y)
        comment = request.env['maeknit.excalidraw.comment'].create(vals)
        self._post_log_note(res_model, int(res_id), field_name,
                            f'Comment added: {message.strip()}',
                            partner_ids=partner_ids or [])
        return {'comment': self._fmt(comment)}

    # ── Resolve (toggle) ──────────────────────────────────────────────────────

    @http.route('/maeknit/excalidraw/comments/resolve', type='json', auth='user')
    def resolve_comment(self, comment_id):
        """Toggle is_resolved on the given comment."""
        comment = request.env['maeknit.excalidraw.comment'].browse(int(comment_id))
        if not comment.exists():
            return {'ok': False, 'error': 'Not found'}
        comment.write({'is_resolved': not comment.is_resolved})
        action = 'resolved' if comment.is_resolved else 'reopened'
        self._post_log_note(comment.res_model, comment.res_id, comment.field_name,
                            f'Comment {action}: {comment.message}')
        return {'ok': True, 'is_resolved': comment.is_resolved}

    # ── Delete ────────────────────────────────────────────────────────────────

    @http.route('/maeknit/excalidraw/comments/delete', type='json', auth='user')
    def delete_comment(self, comment_id):
        """Delete a comment. Only the author or an admin may delete."""
        comment = request.env['maeknit.excalidraw.comment'].browse(int(comment_id))
        if not comment.exists():
            return {'ok': False, 'error': 'Not found'}
        is_author = comment.user_id.id == request.env.user.id
        is_admin = request.env.user.has_group('base.group_system')
        if not (is_author or is_admin):
            return {'ok': False, 'error': 'Forbidden'}
        self._post_log_note(comment.res_model, comment.res_id, comment.field_name,
                            f'Comment deleted: {comment.message}')
        comment.unlink()
        return {'ok': True}

    # ── Helper ────────────────────────────────────────────────────────────────

    def _post_log_note(self, res_model, res_id, field_name, action_text, partner_ids=None):
        """Post a log note to the parent record's chatter."""
        try:
            record = request.env[res_model].browse(res_id)
            if not record.exists() or not hasattr(record, 'message_post'):
                return
            tab_label = _FIELD_LABELS.get(field_name, field_name)
            user_name = request.env.user.name
            body = f'<p><b>[{tab_label}]</b> {user_name}: {action_text}</p>'
            record.message_post(
                body=body,
                message_type='comment',
                subtype_xmlid='mail.mt_note',
                partner_ids=list(partner_ids) if partner_ids else [],
            )
        except Exception:
            _logger.exception("ExcalidrawCommentController: failed to post log note")

    def _fmt(self, comment):
        return {
            'id': comment.id,
            'res_model': comment.res_model,
            'res_id': comment.res_id,
            'field_name': comment.field_name,
            'user_id': comment.user_id.id,
            'user_name': comment.user_id.name or comment.user_id.login,
            'partner_id': comment.partner_id.id,
            'x': comment.x,
            'y': comment.y,
            'element_id': comment.element_id or None,
            'element_frac_x': comment.element_frac_x,
            'element_frac_y': comment.element_frac_y,
            'message': comment.message,
            'is_resolved': comment.is_resolved,
            'create_date': comment.create_date.isoformat() if comment.create_date else None,
        }
