import os

from logging import getLogger

from ckan.plugins import implements, SingletonPlugin
from ckan.plugins import IRoutes
from ckan.plugins import IConfigurer


log = getLogger(__name__)


def configure_template_directory(config, relative_path):
    configure_served_directory(config, relative_path, 'extra_template_paths')

def configure_public_directory(config, relative_path):
    configure_served_directory(config, relative_path, 'extra_public_paths')

def configure_served_directory(config, relative_path, config_var):
    'Configure serving of public/template directories.'
    assert config_var in ('extra_template_paths', 'extra_public_paths')
    this_dir = os.path.dirname(__file__)
    absolute_path = os.path.join(this_dir, relative_path)
    if absolute_path not in config.get(config_var, ''):
        if config.get(config_var):
            config[config_var] += ',' + absolute_path
        else:
            config[config_var] = absolute_path
            
class DgvatForm(SingletonPlugin):
    implements(IRoutes)
    implements(IConfigurer)
    
    def before_map(self, map):
       # map.connect('/dataset/new', controller='ckanext.dgvat.controllers.data_gv_at:PackageDataGvATController', action='new')
       # map.connect('/dataset/edit/{id}', controller='ckanext.dgvat.controllers.data_gv_at:PackageDataGvATController', action='edit')
        map.connect( '/revision/list', controller='ckanext.dgvat.controllers.data_gv_at:myRevisionsFeedGenerator', action = 'list')
        map.connect( '/group/history/{id:.*}', controller='ckanext.dgvat.controllers.data_gv_at:DgvatFeedController', action= 'group')
        #map.connect( '/feed/group/{id}.atom', controller='ckanext.dgvat.controllers.data_gv_at:DgvatFeedController', action='group')
        map.redirect('/user/login', '/', _redirect_code='301 Moved Permanently')
        map.redirect("/users/{url:.*}", '/', _redirect_code='301 Moved Permanently')
        map.redirect("/user/",  '/', _redirect_code='301 Moved Permanently')
        map.redirect('/user/edit', '/', _redirect_code='301 Moved Permanently')
        map.redirect('/user/edit/{id:.*}',  '/', _redirect_code='301 Moved Permanently')
        map.redirect('/user/reset/{id:.*}',  '/', _redirect_code='301 Moved Permanently')
        map.redirect('/user/register',  '/', _redirect_code='301 Moved Permanently')
        map.redirect('/user/login',  '/', _redirect_code='301 Moved Permanently')
        map.redirect('/user/logged_in',  '/', _redirect_code='301 Moved Permanently')
        map.redirect('/user/logged_out', '/', _redirect_code='301 Moved Permanently')
        map.redirect('/user/reset', '/', _redirect_code='301 Moved Permanently')
        map.redirect('/user/me',  '/', _redirect_code='301 Moved Permanently')
        map.redirect('/user/{id:.*}',  '/', _redirect_code='301 Moved Permanently')
        map.redirect('/user',  '/', _redirect_code='301 Moved Permanently')
        map.redirect('ckanadmin_index', '/', _redirect_code='301 Moved Permanently')
        map.redirect('ckanadmin', '/', _redirect_code='301 Moved Permanently')    
        map.redirect('/authorizationgroup/{url:.*}', '/', _redirect_code='301 Moved Permanently')    
        map.redirect('/authorizationgroup', '/', _redirect_code='301 Moved Permanently')
            
        return map
    
    def after_map(self, map):
        return map
    
    def update_config(self, config):
        configure_template_directory(config, 'templates')
        configure_public_directory(config, 'public')
