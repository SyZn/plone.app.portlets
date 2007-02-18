from zope.interface import implements, Interface
from zope.component import adapts, getMultiAdapter, queryUtility

from plone.i18n.normalizer.interfaces import IIDNormalizer
from plone.portlets.interfaces import IPortletDataProvider
from plone.app.portlets.portlets import base

from zope import schema
from zope.formlib import form

from plone.memoize.instance import memoize

from Acquisition import aq_inner, aq_base, aq_parent
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from Products.CMFCore.utils import getToolByName

from Products.CMFPlone.interfaces import INonStructuralFolder
from Products.CMFPlone import utils
from Products.CMFPlone import PloneMessageFactory as _

from plone.app.layout.navigation.interfaces import INavtreeStrategy
from plone.app.layout.navigation.interfaces import INavigationQueryBuilder

from plone.app.layout.navigation.root import getNavigationRoot
from plone.app.layout.navigation.navtree import buildFolderTree

from Products.CMFPlone.browser.navtree import SitemapNavtreeStrategy

class INavigationPortlet(IPortletDataProvider):
    """A portlet which can render the navigation tree
    """
    
    name = schema.TextLine(
            title=_(u"Title"),
            description=_(u"The title of the navigation tree. Leave blank for the default, translated title"),
            default=u"",
            required=False)
    
    root = schema.TextLine(
            title=_(u"Root path"),
            description=_(u"A path that specifies the base folder where the navigation tree, sitemap, breadcrumbs "
                            "and tabs will be rooted. Use '/' for the portal root, and '/folder1' to start at 'folder1'."),
            default=u"",
            required=False)
                            
    currentFolderOnly = schema.Bool(
            title=_(u"Current folder only"),
            description=_(u"If selected, the navigation tree will only show the current folder and its children at all times."),
            default=False,
            required=False)
    
    topLevel = schema.Int(
            title=_(u"Start level"),
            description=_(u"An integer value that specifies the number of folder "
                           "levels below the site root that must be exceeded before "
                           "the navigation tree will display. 0 means that the navigation "
                           "tree should be displayed everywhere including pages in the root "
                           "of the site. 1 means the tree only shows up inside folders located "
                           "in the root and downwards, never showing at the top level."),
            default=0,
            required=False)
    
    bottomLevel = schema.Int(
            title=_(u"Depth"),
            description=_(u"How many folders should be included before the navigation "
                           "tree stops. 0 means no limit. 1 only includes the root folder."),
            default=0,
            required=False)

class Assignment(base.Assignment):
    implements(INavigationPortlet)

    title = _(u'Navigation portlet')
    
    def __init__(self, name=u"", root=u"", currentFolderOnly=False, topLevel=0, bottomLevel=0):
        self.name = name
        self.root = root
        self.currentFolderOnly = currentFolderOnly
        self.topLevel = topLevel
        self.bottomLevel = bottomLevel

class Renderer(base.Renderer):

    def __init__(self, context, request, view, manager, data):
        base.Renderer.__init__(self, context, request, view, manager, data)
        
        self.properties = getToolByName(context, 'portal_properties').navtree_properties
        self.urltool = getToolByName(context, 'portal_url')
        
    def title(self):
        return self.data.name or self.properties.name

    def display(self):
        tree = self.getNavTree()
        root = self.getNavRoot()
        return (root is not None and len(tree['children']) > 0)

    def include_top(self):
        return self.properties.includeTop

    def navigation_root(self):
        return self.getNavRoot()

    def root_type_name(self):
        root = self.getNavRoot()
        return queryUtility(IIDNormalizer).normalize(root.portal_type)

    def root_item_class(self):
        context = aq_inner(self.context)
        root = self.getNavRoot()
        if (aq_base(root) is aq_base(context) or
                (aq_base(root) is aq_base(aq_parent(aq_inner(context))) and
                utils.isDefaultPage(context, self.request, context))):
            return 'navTreeCurrentItem'
        else:
            return ''
            
    def root_icon(self):
        portal = self.urltool.getPortalObject()
        ploneview = getMultiAdapter((self.context, self.request), name=u'plone')
        icon = ploneview.getIcon(portal)
        return icon.url
            
    def root_is_portal(self):
        root = self.getNavRoot()
        return aq_base(root) is aq_base(self.urltool.getPortalObject())

    def createNavTree(self):
        data = self.getNavTree()
        
        bottomLevel = self.data.bottomLevel or self.properties.getProperty('bottomLevel', 0)

        return self.recurse(children=data.get('children', []), level=1, bottomLevel=bottomLevel)

    # Cached lookups

    @memoize
    def getNavRoot(self, _marker=[]):
        portal = self.urltool.getPortalObject()

        currentFolderOnly = self.data.currentFolderOnly or self.properties.getProperty('currentFolderOnlyInNavtree', False)
        topLevel = self.data.topLevel or self.properties.getProperty('topLevel', 0)
        
        rootPath = getRootPath(self.context, currentFolderOnly, topLevel, self.data.root)
        
        if rootPath == self.urltool.getPortalPath():
            return portal
        else:
            try:
                return portal.unrestrictedTraverse(rootPath)
            except (AttributeError, KeyError,):
                return portal

    @memoize
    def getNavTree(self, _marker=[]):
        context = aq_inner(self.context)
        
        queryBuilder = getMultiAdapter((context, self.data), INavigationQueryBuilder)
        strategy = getMultiAdapter((context, self.data), INavtreeStrategy)

        return buildFolderTree(context, obj=context, query=queryBuilder(), strategy=strategy)

    def update(self):
        pass

    render = ViewPageTemplateFile('navigation.pt')
    recurse = ViewPageTemplateFile('navigation_recurse.pt')

class AddForm(base.AddForm):
    form_fields = form.Fields(INavigationPortlet)
    label = _(u"Add Navigation portlet")
    description = _(u"This portlet display a navigation tree.")

    def create(self, data):
        return Assignment(name=data.get('name', u""),
                          root=data.get('root', u""),
                          currentFolderOnly=data.get('currentFolderOnly', False),
                          topLevel=data.get('topLevel', 0),
                          bottomLevel=data.get('bottomLevel', 0))

class EditForm(base.EditForm):
    form_fields = form.Fields(INavigationPortlet)
    label = _(u"Edit Navigation portlet")
    description = _(u"This portlet display a navigation tree.")
    
class QueryBuilder(object):
    """Build a navtree query based on the settings in navtree_properties
    and those set on the portlet.
    """
    implements(INavigationQueryBuilder)
    adapts(Interface, INavigationPortlet)

    def __init__(self, context, portlet):
        self.context = context
        self.portlet = portlet
        
        portal_properties = getToolByName(context, 'portal_properties')
        navtree_properties = getattr(portal_properties, 'navtree_properties')
        
        portal_url = getToolByName(context, 'portal_url')
        
        # Acquire a custom nav query if available
        customQuery = getattr(context, 'getCustomNavQuery', None)
        if customQuery is not None and utils.safe_callable(customQuery):
            query = customQuery()
        else:
            query = {}

        # Construct the path query

        rootPath = getNavigationRoot(context, relativeRoot=portlet.root)
        currentPath = '/'.join(context.getPhysicalPath())

        # If we are above the navigation root, a navtree query would return
        # nothing (since we explicitly start from the root always). Hence,
        # use a regular depth-1 query in this case.

        if not currentPath.startswith(rootPath):
            query['path'] = {'query' : rootPath, 'depth' : 1}
        else:
            query['path'] = {'query' : currentPath, 'navtree' : 1}

        topLevel = portlet.topLevel or navtree_properties.getProperty('topLevel', 0)
        if topLevel and topLevel > 0:
             query['path']['navtree_start'] = topLevel + 1

        # XXX: It'd make sense to use 'depth' for bottomLevel, but it doesn't
        # seem to work with EPI.

        # Only list the applicable types
        query['portal_type'] = utils.typesToList(context)

        # Apply the desired sort
        sortAttribute = navtree_properties.getProperty('sortAttribute', None)
        if sortAttribute is not None:
            query['sort_on'] = sortAttribute
            sortOrder = navtree_properties.getProperty('sortOrder', None)
            if sortOrder is not None:
                query['sort_order'] = sortOrder

        # Filter on workflow states, if enabled
        if navtree_properties.getProperty('enable_wf_state_filtering', False):
            query['review_state'] = navtree_properties.getProperty('wf_states_to_show', ())

        self.query = query

    def __call__(self):
        return self.query
        
class NavtreeStrategy(SitemapNavtreeStrategy):
    """The navtree strategy used for the default navigation portlet
    """
    implements(INavtreeStrategy)
    adapts(Interface, INavigationPortlet)

    def __init__(self, context, portlet):
        SitemapNavtreeStrategy.__init__(self, context, portlet)
        portal_properties = getToolByName(context, 'portal_properties')
        navtree_properties = getattr(portal_properties, 'navtree_properties')
        
        # XXX: We can't do this with a 'depth' query to EPI...
        self.bottomLevel = portlet.bottomLevel or navtree_properties.getProperty('bottomLevel', 0)

        currentFolderOnly = portlet.currentFolderOnly or navtree_properties.getProperty('currentFolderOnlyInNavtree', False)
        topLevel = portlet.topLevel or navtree_properties.getProperty('topLevel', 0)
        self.rootPath = getRootPath(context, currentFolderOnly, topLevel, portlet.root)

    def subtreeFilter(self, node):
        sitemapDecision = SitemapNavtreeStrategy.subtreeFilter(self, node)
        if sitemapDecision == False:
            return False
        depth = node.get('depth', 0)
        if depth > 0 and self.bottomLevel > 0 and depth >= self.bottomLevel:
            return False
        else:
            return True
            
def getRootPath(context, currentFolderOnly, topLevel, root):
    """Helper function to calculate the real root path
    """
    context = aq_inner(context)
    if currentFolderOnly:
        folderish = getattr(aq_base(context), 'isPrincipiaFolderish', False) and not INonStructuralFolder.providedBy(context)
        if folderish:
            return '/'.join(context.getPhysicalPath())
        else:
            return '/'.join(aq_parent(context).getPhysicalPath())

    rootPath = getNavigationRoot(context, relativeRoot=root)

    # Adjust for topLevel
    if topLevel > 0:
        contextPath = '/'.join(context.getPhysicalPath())
        if not contextPath.startswith(rootPath):
            return None
        contextSubPathElements = contextPath[len(rootPath)+1:].split('/')
        if len(contextSubPathElements) < topLevel:
            return None
        rootPath = rootPath + '/' + '/'.join(contextSubPathElements[:topLevel])
    
    return rootPath