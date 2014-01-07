# -*- coding: utf-8 -*- 


from ckan.controllers.package import PackageController
from ckan.controllers.revision import RevisionController
from ckan.controllers.feed import FeedController
from ckan.controllers.group import GroupController
from ckan.lib.base import BaseController, c, model, request, render, h, g
from ckan.lib.base import ValidationException, abort, gettext
from ckan.lib.navl.validators import ignore_missing, not_empty, keep_extras
from ckan.logic.converters import convert_to_extras
from ckan.logic.schema import package_form_schema
from ckan.logic import NotFound, NotAuthorized, ValidationError
from ckan.logic import check_access, get_action
from pylons.i18n import get_lang, _
from webhelpers.feedgenerator import Atom1Feed
from ckan import model
import logging
import datetime
from datetime import datetime, timedelta
import urlparse

import webhelpers.feedgenerator
from pylons import config
from urllib import urlencode

from ckan import model
from ckan.lib.base import BaseController, c, request, response, json, abort, g
from ckan.lib.helpers import date_str_to_datetime, url_for
from ckan.logic import get_action, NotFound



log = logging.getLogger(__name__)


def _package_search(data_dict):
    """
    Helper method that wraps the package_search action.

     * unless overridden, sorts results by metadata_modified date
     * unless overridden, sets a default item limit
    """
    context = {'model': model, 'session': model.Session,
               'user': c.user or c.author}

    if 'sort' not in data_dict or not data_dict['sort']:
        data_dict['sort'] = 'metadata_modified desc'

    if 'rows' not in data_dict or not data_dict['rows']:
        data_dict['rows'] = ITEMS_LIMIT

    # package_search action modifies the data_dict, so keep our copy intact.
    query = get_action('package_search')(context,data_dict.copy())

    return query['count'], query['results']

def _create_atom_id(resource_path, authority_name=None, date_string=None):
    """
    Helper method that creates an atom id for a feed or entry.

    An id must be unique, and must not change over time.  ie - once published,
    it represents an atom feed or entry uniquely, and forever.  See [4]:

        When an Atom Document is relocated, migrated, syndicated,
        republished, exported, or imported, the content of its atom:id
        element MUST NOT change.  Put another way, an atom:id element
        pertains to all instantiations of a particular Atom entry or feed;
        revisions retain the same content in their atom:id elements.  It is
        suggested that the atom:id element be stored along with the
        associated resource.

    resource_path
        The resource path that uniquely identifies the feed or element.  This
        mustn't be something that changes over time for a given entry or feed.
        And does not necessarily need to be resolvable.

        e.g. ``"/group/933f3857-79fd-4beb-a835-c0349e31ce76"`` could represent
        the feed of datasets belonging to the identified group.

    authority_name
        The domain name or email address of the publisher of the feed.  See [3]
        for more details.  If ``None`` then the domain name is taken from the
        config file.  First trying ``ckan.feeds.authority_name``, and failing
        that, it uses ``ckan.site_url``.  Again, this should not change over time.

    date_string
        A string representing a date on which the authority_name is owned by the
        publisher of the feed.

        e.g. ``"2012-03-22"``

        Again, this should not change over time.

        If date_string is None, then an attempt is made to read the config
        option ``ckan.feeds.date``.  If that's not available,
        then the date_string is not used in the generation of the atom id.

    Following the methods outlined in [1], [2] and [3], this function produces
    tagURIs like: ``"tag:thedatahub.org,2012:/group/933f3857-79fd-4beb-a835-c0349e31ce76"``.

    If not enough information is provide to produce a valid tagURI, then only
    the resource_path is used, e.g.: ::

        "http://thedatahub.org/group/933f3857-79fd-4beb-a835-c0349e31ce76"

    or

        "/group/933f3857-79fd-4beb-a835-c0349e31ce76"

    The latter of which is only used if no site_url is available.   And it should
    be noted will result in an invalid feed.

    [1] http://web.archive.org/web/20110514113830/http://diveintomark.org/archives/2004/05/28/howto-atom-id
    [2] http://www.taguri.org/
    [3] http://tools.ietf.org/html/rfc4151#section-2.1
    [4] http://www.ietf.org/rfc/rfc4287
    """
    if authority_name is None:
        authority_name = config.get('ckan.feeds.authority_name', '').strip()
        if not authority_name:
            site_url = config.get('ckan.site_url', '').strip()
            authority_name = urlparse.urlparse(site_url).netloc

    if not authority_name:
        log.warning('No authority_name available for feed generation.  '
                    'Generated feed will be invalid.')

    if date_string is None:
        date_string = config.get('ckan.feeds.date', '')

    if not date_string:
        log.warning('No date_string available for feed generation.  '
                    'Please set the "ckan.feeds.date" config value.')

        # Don't generate a tagURI without a date as it wouldn't be valid.
        # This is best we can do, and if the site_url is not set, then
        # this still results in an invalid feed.
        site_url = config.get('ckan.site_url', '')
        return '/'.join([site_url, resource_path])

    tagging_entity = ','.join([authority_name, date_string])
    return ':'.join(['tag', tagging_entity, resource_path])



class PackageDataGvATController(PackageController):
    package_form = 'package/datagvat_form.html'
    log.debug("Enter: PackageDataGvATController")
    
class feedGroupController(GroupController):

    def history(self, id):
        if 'diff' in request.params or 'selected1' in request.params:
            try:
                params = {'id':request.params.getone('group_name'),
                          'diff':request.params.getone('selected1'),
                          'oldid':request.params.getone('selected2'),
                          }
            except KeyError, e:
                if dict(request.params).has_key('group_name'):
                    id = request.params.getone('group_name')
                c.error = _('Select two revisions before doing the comparison.')
            else:
                params['diff_entity'] = 'group'
                h.redirect_to(controller='revision', action='diff', **params)

        context = {'model': model, 'session': model.Session,
                   'user': c.user or c.author,
                   'schema': self._form_to_db_schema()}
        data_dict = {'id': id}
        try:
            c.group_dict = get_action('group_show')(context, data_dict)
            c.group_revisions = get_action('group_revision_list')(context, data_dict)
            c.group = context['group']
        except NotFound:
            abort(404, _('Group not found'))
        except NotAuthorized:
            abort(401, _('User %r not authorized to edit %r') % (c.user, id))

        onlycreated = request.params.get('created', '')
        feed_title=u'RSS-Feed - Geänderte Datensätze - %s - data.gv.at' % c.group_dict['display_name']
        feed_description=_(u'Letzte Änderungen: ') + c.group_dict['display_name']
        if onlycreated == '1':
            feed_title=u'RSS-Feed - Neue Datensätze - %s - data.gv.at' % c.group_dict['display_name']
            feed_description=_(u'Neue Datensätze: ') + c.group_dict['display_name']
        format = request.params.get('format', '')
        if format == 'atom':
            # Generate and return Atom 1.0 document.
            from webhelpers.feedgenerator import Atom1Feed
            feed = Atom1Feed(
                title=_(u'CKAN Group Revision History'),
                link=h.url_for(controller='group', action='read', id=c.group_dict['name']),
                description=_(u'Recent changes to CKAN Group: ') +
                    c.group_dict['display_name'],
                language=unicode(get_lang()),
            )
            for revision_dict in c.group_revisions:
                revision_date = h.date_str_to_datetime(revision_dict['timestamp'])
                try:
                    dayHorizon = int(request.params.get('days'))
                except:
                    dayHorizon = 30
                dayAge = (datetime.datetime.now() - revision_date).days
                if dayAge >= dayHorizon:
                    break
                if revision_dict['message']:
                    item_title = u'%s' % revision_dict['message'].split('\n')[0]
                else:
                    item_title = u'%s' % revision_dict['id']
                item_link = h.url_for(controller='revision', action='read', id=revision_dict['id'])
                item_description = _('Log message: ')
                item_description += '%s' % (revision_dict['message'] or '')
                item_author_name = revision_dict['author']
                item_pubdate = revision_date
                feed.add_item(
                    title=item_title,
                    link=item_link,
                    description=item_description,
                    author_name=item_author_name,
                    pubdate=item_pubdate,
                )
            feed.content_type = 'application/atom+xml'
            return feed.writeString('utf-8')
        return render( self._history_template(c.group_dict['type']) )    
    
    def history_old(self, id):
        if 'diff' in request.params or 'selected1' in request.params:
            try:
                params = {'id':request.params.getone('group_name'),
                          'diff':request.params.getone('selected1'),
                          'oldid':request.params.getone('selected2'),
                          }
            except KeyError, e:
                if dict(request.params).has_key('group_name'):
                    id = request.params.getone('group_name')
                c.error = _('Select two revisions before doing the comparison.')
            else:
                params['diff_entity'] = 'group'
                h.redirect_to(controller='revision', action='diff', **params)

        context = {'model': model, 'session': model.Session,
                   'user': c.user or c.author,
                   'schema': self._form_to_db_schema()}
        data_dict = {'id': id}
        try:
            c.group_dict = get_action('group_show')(context, data_dict)
            c.group_revisions = get_action('group_revision_list')(context, data_dict)
            # Still necessary for the authz check in group/layout.html
            c.group = context['group']
        except NotFound:
            abort(404, _('Group not found'))
        except NotAuthorized:
            abort(401, _('User %r not authorized to edit %r') % (c.user, id))
            
        onlycreated = request.params.get('created', '')
        feed_title=u'RSS-Feed - Geänderte Datensätze - %s - data.gv.at' % c.group_dict['display_name']
        feed_description=_(u'Letzte Änderungen: ') + c.group_dict['display_name']
        if onlycreated == '1':
            feed_title=u'RSS-Feed - Neue Datensätze - %s - data.gv.at' % c.group_dict['display_name']
            feed_description=_(u'Neue Datensätze: ') + c.group_dict['display_name']
        format = request.params.get('format', '')
        if format == 'atom':
            # Generate and return Atom 1.0 document.
            from webhelpers.feedgenerator import Atom1Feed
            feed = Atom1Feed(
                title=feed_title,
                link=h.url_for(controller='group', action='read', id=c.group_dict['name']),
                description=feed_description,
                language=unicode(get_lang()),
            )
            for revision_dict in c.group_revisions:
                
                revision_date = h.date_str_to_datetime(revision_dict['timestamp'])
                try:
                    dayHorizon = int(request.params.get('days'))
                except:
                    dayHorizon = 30
                dayAge = (datetime.now() - revision_date).days
                if dayAge >= dayHorizon:
                    break
                if revision_dict['message']:
                    item_title = u'%s' % revision_dict['message'].split('\n')[0]
                else:
                    item_title = u'%s' % revision_dict['id']
                if onlycreated=='1' and not item_title == 'Neuer Datensatz erstellt.':
                    continue
                log.fatal(revision_dict)
                item_link = h.url_for(controller='revision', action='read', id=revision_dict['id'])
                item_description = _('Log message: ')
                item_description += '%s' % (revision_dict['message'] or '')
                item_author_name = revision_dict['author']
                item_pubdate = revision_date
                feed.add_item(
                    title=item_title,
                    link=item_link,
                    description=item_description,
                    author_name=item_author_name,
                    pubdate=item_pubdate,
                )
            feed.content_type = 'application/atom+xml'
            return feed.writeString('utf-8')
        return render( self._history_template(c.group_dict['type']) )
    
class myRevisionsFeedGenerator(RevisionController):

    def list(self):
        format = request.params.get('format', '')
        onlycreated = request.params.get('created', '')
        organization = request.params.get('organization', '')
        feed_title=u'RSS-Feed - Geänderte Datensätze - data.gv.at'
        feed_description=_(u'Letzte Änderungen: ')
        if onlycreated == '1':
            feed_title=u'RSS-Feed - Neue Datensätze - data.gv.at'
            feed_description=_(u'Neue Datensätze: ')
        log.debug("organization selected: %s" % organization)        
        if format == 'atom':
            # Generate and return Atom 1.0 document.
            from webhelpers.feedgenerator import Atom1Feed
            feed = Atom1Feed(
                title=feed_title,
                link=h.url_for(controller='revision', action='list', id=''),
                description=feed_description,
                language=unicode(get_lang()),
            )
            # TODO: make this configurable?
            # we do not want the system to fall over!
            maxresults = 200
            maxfeedresults = 10
            try:
                dayHorizon = int(request.params.get('days', 30))
            except:
                dayHorizon = 30
            ourtimedelta = timedelta(days=-dayHorizon)
            since_when = datetime.now() + ourtimedelta
            querycounter = 0
            while querycounter <= 2:
                revision_query = model.repo.history()
                revision_query = revision_query.filter(
                        model.Revision.timestamp>=since_when).filter(
                        model.Revision.id!=None)
                revision_query = revision_query.slice(maxresults*querycounter, maxresults*querycounter+maxresults)
                for revision in revision_query:
                    if(feed.num_items()>=maxfeedresults):
                           break
                    package_indications = []
                    revision_changes = model.repo.list_changes(revision)
                    resource_revisions = revision_changes[model.Resource]
                    resource_group_revisions = revision_changes[model.ResourceGroup]
                    package_extra_revisions = revision_changes[model.PackageExtra]
                    for package in revision.packages:
                        number = len(package.all_revisions)
                        package_revision = None
                        count = 0
                        for pr in package.all_revisions:
                            count += 1
                            if pr.revision.id == revision.id:
                                package_revision = pr
                                break
                        if package_revision and package_revision.state == model.State.DELETED:
                            transition = 'deleted'
                        elif package_revision and count == number:
                            transition = 'created'
                        else:
                            transition = 'updated'
                            for resource_revision in resource_revisions:
                                if resource_revision.continuity.resource_group.package_id == package.id:
                                    transition += ':resources'
                                    break
                            for resource_group_revision in resource_group_revisions:
                                if resource_group_revision.package_id == package.id:
                                    transition += ':resource_group'
                                    break
                            for package_extra_revision in package_extra_revisions:
                                if package_extra_revision.package_id == package.id:
                                    if package_extra_revision.key == 'date_updated':
                                        transition += ':date_updated'
                                        break
                        indication = "%s:%s" % (package.name, transition)
                        package_indications.append(indication)
                        packName = package.name
                        packId = package.id
    #                    packTitle = package.title
    #                    maintainer = package.maintainer
    #                    package_indications.append(indication)
    #                    package = model.Package.get(packId)
    #                    packDict = model.Package.as_dict(package)
                    if (onlycreated == '1') and not(transition.startswith('created')):
                        log.fatal("show only created")
                        log.fatal("transition: %s" % transition)
                        continue
                    
    #                log.debug('group found: %s / group wanted: %s' % (packDict.get('groups'), organization))                   
    #                if (organization != ''):
    #                    if not(organization in packDict.get('groups')):
    #                        continue
    #                log.critical('CORRECT GROUP FOUND!!')                    
                    pkgs = u'[%s]' % ' '.join(package_indications)
                    item_title = u'r%s ' % (revision.id)
                    item_title += pkgs
                    if revision.message:
                        item_title += ': %s' % (revision.message or '')
                    item_link = "/sucheDetail/?id=%s" % packId
                    item_description = _('Datasets affected: %s.\n') % pkgs
                    item_description += '%s' % (revision.message or '')
                    item_author_name = revision.author
                    item_pubdate = revision.timestamp
                    feed.add_item(
                        title=item_title,
                        link=item_link,
                        description=item_description,
                        author_name=item_author_name,
                        pubdate=item_pubdate,
                    )
                querycounter += 1
            feed.content_type = 'application/atom+xml'
            return feed.writeString('utf-8')
        else:
            query = model.Session.query(model.Revision)
            c.page = Page(
                collection=query,
                page=request.params.get('page', 1),
                url=h.pager_url,
                items_per_page=20
            )
            return render('revision/list.html')
    
    
    
    def old_list(self):
           format = request.params.get('format', '')
           onlycreated = request.params.get('created', '')
           organization = request.params.get('organization', '')
           feed_title=u'RSS-Feed - Geänderte Datensätze - data.gv.at'
           feed_description=_(u'Letzte Änderungen: ')
           if onlycreated == '1':
               feed_title=u'RSS-Feed - Neue Datensätze - data.gv.at'
               feed_description=_(u'Neue Datensätze: ')
           log.debug("organization selected: %s" % organization)
           lang = get_lang()
           if lang[0]:
               lang = lang[0]
           if format == 'atom':
               feed = Atom1Feed(
                  title=_(feed_title),
                  link=h.url_for(controller='revision', action='list', id=''),
                  description=feed_description,
                  language=unicode(lang),
               )
               maxresults = 10
               #revision_query = model.repo.history()
               #revision_query = revision_query.limit(maxresults)
               revision_query = model.repo.history()
               revision_query = revision_query.order_by(model.Revision.timestamp.desc())
               revision_query = revision_query.filter(model.Revision.id!=None)
               #revision_query = revision_query.filter(model.Member.group_id=='4a766e5e-89a3-4a16-addd-05fa0b5953c3')
               #revision_query = revision_query.limit(maxresults)
               maintainer = 'default'
               for revision in revision_query:
                   if(feed.num_items()>=maxresults):
                       break
                   transition = ""
                   packName= ""
                   package_indications = []
                   revision_changes = model.repo.list_changes(revision)
                   resource_revisions = revision_changes[model.Resource]
                   #package_revisions = revision_changes[model.Package]
                   resource_group_revisions = revision_changes[model.ResourceGroup]
                   package_extra_revisions = revision_changes[model.PackageExtra]
                   group_revisions = revision_changes[model.Group]
                   tag_revisions = revision_changes[model.PackageTag]
                   member_revisions = revision_changes[model.Member]
                   
                   #Skip groups
                   if (len(group_revisions)>0):
                     continue       
                   #if (len(member_revisions)>0):
                     #continue   
                   if len(revision.packages)==0:
                     continue
                   if (len(resource_group_revisions) + len(tag_revisions) +len(package_extra_revisions) +len(resource_revisions))==0:
                     continue       
                   for package in revision.packages:
                       number = len(package.all_revisions)
                       package_revision = None
                       count = 0
                       
                       for pr in package.all_revisions:
                           count += 1
                           if pr.revision.id == revision.id:
                               package_revision = pr
                               break
                       if package_revision and package_revision.state == model.State.DELETED:
                            transition = 'deleted'
                       elif package_revision and count == number:
                            transition = 'created'
                       else:
                            transition = 'updated'
                            for resource_revision in resource_revisions:
                                if resource_revision.continuity.resource_group.package_id == package.id:
                                    transition += ': Ressourcen'
                                    break
                            for resource_group_revision in resource_group_revisions:
                                if resource_group_revision.package_id == package.id:
                                    transition += ' resource_group'
                                    break
                            for package_extra_revision in package_extra_revisions:
                                if package_extra_revision.package_id == package.id:
                                    #if package_extra_revision.key == 'date_updated':
                                    transition += ''
                                    break
                       indication = "%s" % ( transition)
                       packName = package.name
                       packId = package.id
                       packTitle = package.title
                       maintainer = package.maintainer
                       package_indications.append(indication)
                       package = model.Package.get(packId)
                       packDict = model.Package.as_dict(package)
                   if (onlycreated == '1') and not(transition.startswith('created')):
                       continue

                   log.debug('group found: %s / group wanted: %s' % (packDict.get('groups'), organization))                   
                   if (organization != ''):
                       if not(organization in packDict.get('groups')):
                           continue
                   log.critical('CORRECT GROUP FOUND!!')
                   #if len(package_indications[0]) < 3:
                   #    revision_changes.xxx()
                       
                   pkgs = u'%s' % ' '.join(package_indications)
                   #item_title = u'%s ' % (revision.id)
                   item_title = packTitle
                   #if revision.message:
                   #    item_title += ': %s' % (revision.message or '')    
                   item_link = '/sucheDetail/?id=' + packId
                   item_description = indication
                   #item_description = _('Datasets affected: %s.\n') % pkgs
                   #item_description += '%s' % (revision.message or '')
                   #item_author_name = Authorization Group !
                   item_author_name =  maintainer
                   item_pubdate = revision.timestamp
                   
                   feed.add_item(
                     title=item_title,
                     link=item_link,
                     description=item_description,
                     author_name=item_author_name,
                     pubdate=item_pubdate,
                   )
                   log.fatal("feedlength: " + feed.num_items())
               feed.content_type = 'application/atom+xml'
               return feed.writeString('utf-8')
           else:
               return RevisionController.list(self);
           
           
class DgvatFeedController(FeedController):
    
    def group(self,id):

        try:
            context = {'model': model, 'session': model.Session,
               'user': c.user or c.author}
            group_dict = get_action('group_show')(context,{'id':id})
        except NotFound:
            abort(404,'Group not found')

        
        data_dict, params = self._parse_url_params()
        data_dict['fq'] = 'groups:"%s"' % id
        
        log.fatal(data_dict)
        
        item_count, results = _package_search(data_dict)

        navigation_urls = self._navigation_urls(params,
                                                item_count=item_count,
                                                limit=data_dict['rows'],
                                                controller='feed',
                                                action='group',
                                                id=id)

        feed_url = self._feed_url(params,
                                  controller='feed',
                                  action='group',
                                  id=id)

        alternate_url = self._alternate_url(params, groups=id)

        return self.output_feed(results,
                    feed_title = u'%s - Group: "%s"' % (g.site_title, group_dict['title']),
                    feed_description = u'Recently created or updated datasets on %s by group: "%s"' % \
                        (g.site_title,group_dict['title']),
                    feed_link = alternate_url,
                    feed_guid = _create_atom_id(u'/feeds/groups/%s.atom' % id),
                    feed_url = feed_url,
                    navigation_urls = navigation_urls,
                )    