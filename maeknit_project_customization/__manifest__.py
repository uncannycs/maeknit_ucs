# -*- coding: utf-8 -*-
{
  'name': 'Maeknit Project Customization',
  'version': '1.0.0',
  'summary': 'Makes user_ids field editable in task list view and adds project categorization',
  'description': '''
      This module makes the user_ids field editable in the enterprise task list view.
      It modifies the view of Tasks and Projects.
      Adds 'Client Projects' and 'Internal Projects' categories.
      Disables stages in favor of task status.
  ''',
  'category': 'Project',
  'author': 'Mahimul Islam (Maeknit)',
  'website': 'https://maeknit.io',
  'depends': ['project'],
  'data': ['views/project_task_views.xml',
           'views/project_views.xml'],
  'assets': {
      'web.assets_backend': [
          'maeknit_project_customization/static/src/js/project_project_list_renderer_custom.js',
      ],
  },
  'installable': True,
  'application': False,
  'auto_install': False,
  'license': 'LGPL-3',
}
