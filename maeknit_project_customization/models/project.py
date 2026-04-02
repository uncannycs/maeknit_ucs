from odoo import models, api, fields
import ast
import logging

class Project(models.Model):
  _inherit = 'project.project'
  project_type = fields.Selection([
    ('client', 'Client Project'),
    ('internal', 'Internal Project'),
    ], string='Project Type', default='client', required=True,
    help="Categorizes projects as client-facing or internal.")


  def action_view_tasks(self):
      """Override to set list view as default for tasks."""
      action = super(Project, self).action_view_tasks()
              
      # Change the view_mode to have list first
      if action.get('view_mode'):
          view_modes = action['view_mode'].split(',')
          if 'list' in view_modes:
              view_modes.remove('list')
              view_modes.insert(0, 'list')
              action['view_mode'] = ','.join(view_modes)
      
      # Also update the views list to match the new order
      if action.get('views'):
          views = action['views']
          list_view = None
          for i, view in enumerate(views):
              if view[1] == 'list':
                  list_view = views.pop(i)
                  break
          
          if list_view:
              views.insert(0, list_view)
              action['views'] = views
      
      # Make sure the context includes view_type=list
      if not action.get('context'):
          action['context'] = {}
      
      if isinstance(action['context'], dict):
          action['context'].update({'view_type': 'list'})
      else:
          # If context is a string, we need to handle it differently
          ctx = eval(action['context']) if action['context'] else {}
          ctx.update({'view_type': 'list'})
          action['context'] = str(ctx)
              
      return action

  def action_open_project_form(self):
      """Open the project form view in a new window."""
      self.ensure_one()
      return {
          'type': 'ir.actions.act_window',
          'res_model': 'project.project',
          'res_id': self.id,
          'view_mode': 'form',
          'name': self.name,
          'target': 'current', # Open in current window
      }
