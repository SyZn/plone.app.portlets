from Acquisition import aq_inner
from plone.app.portlets import PloneMessageFactory as _
from plone.app.portlets.portlets import base
from plone.i18n.normalizer.interfaces import IIDNormalizer
from plone.memoize.instance import memoize
from plone.portlets.interfaces import IPortletDataProvider
from Products.CMFCore.utils import getToolByName
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from zope.component import getMultiAdapter
from zope.component import queryUtility
from zope.interface import implements


class IReviewPortlet(IPortletDataProvider):
    pass


class Assignment(base.Assignment):
    implements(IReviewPortlet)

    @property
    def title(self):
        return _(u"Review list")


class Renderer(base.Renderer):

    render = ViewPageTemplateFile('review.pt')

    title = _('box_review_list', default=u"Review List")

    @property
    def anonymous(self):
        context = aq_inner(self.context)
        portal_state = getMultiAdapter((context, self.request),
                                       name='plone_portal_state')
        return portal_state.anonymous()

    @property
    def available(self):
        return not self.anonymous and len(self._data())

    def review_items(self):
        return self._data()

    def full_review_link(self):
        context = aq_inner(self.context)
        mtool = getToolByName(context, 'portal_membership')
        # check if user is allowed to Review Portal Content here
        if mtool.checkPermission('Review portal content', context):
            return '%s/full_review_list' % context.absolute_url()
        else:
            return None

    @memoize
    def _data(self):
        if self.anonymous:
            return []
        context = aq_inner(self.context)
        workflow = getToolByName(context, 'portal_workflow')

        plone_view = getMultiAdapter((context, self.request), name='plone')
        getMember = getToolByName(context, 'portal_membership').getMemberById
        toLocalizedTime = plone_view.toLocalizedTime

        idnormalizer = queryUtility(IIDNormalizer)
        norm = idnormalizer.normalize
        objects = workflow.getWorklistsResults()
        items = []
        for obj in objects:
            review_state = workflow.getInfoFor(obj, 'review_state')
            creator_id = obj.Creator()
            creator = getMember(creator_id)
            if creator:
                creator_name = creator.getProperty('fullname', '') or creator_id
            else:
                creator_name = creator_id
            hasImage = True if getattr(obj,'image',None) else False
            items.append(dict(
                path=obj.absolute_url(),
                title=obj.pretty_title_or_id(),
                item_class = 'contenttype-' + norm(obj.portal_type),
                description=obj.Description(),
                creator=creator_name,
                review_state=review_state,
                review_state_class='state-%s ' % norm(review_state),
                mod_date=toLocalizedTime(obj.ModificationDate()),
                hasImage = hasImage,                    
            ))
        return items


class AddForm(base.NullAddForm):
    schema = IReviewPortlet
    label = _(u"Add Review Portlet")
    description = _(u"This portlet displays a queue of documents awaiting "
                    u"review.")

    def create(self):
        return Assignment()
