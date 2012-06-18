# -*- coding: utf-8 -*-
##
##
## This file is part of Indico.
## Copyright (C) 2002 - 2014 European Organization for Nuclear Research (CERN).
##
## Indico is free software; you can redistribute it and/or
## modify it under the terms of the GNU General Public License as
## published by the Free Software Foundation; either version 3 of the
## License, or (at your option) any later version.
##
## Indico is distributed in the hope that it will be useful, but
## WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
## General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with Indico;if not, see <http://www.gnu.org/licenses/>.

from MaKaC import conference
from indico.core.config import Config
from MaKaC.common.output import outputGenerator
from MaKaC import accessControl
from indico.util.event import uniqueId

class MARCXMLGenerator:
    """
    Generates MARCXML based on Indico DB objects
    """

    def  __init__(self, XG):
        # self.categoryRoot = conference.CategoryManager().getRoot()
        self._user = accessControl.AccessWrapper()
        self._XMLGen = XG
        self._config = Config.getInstance()
        self._outGen = outputGenerator(self._user, self._XMLGen)

    def setPermissionsOf(self, avatar):
        """
        Sets access level according to avatar
        """
        self._user.setUser(avatar)

    def generateDeleted(self, recId, out=None):
        if not out:
            out = self._XMLGen

        if type(recId) != str:
            raise AttributeError("Expected int id, got '%s'" % recId)

        out.openTag("record")

        out.openTag("datafield",[["tag","970"],["ind1"," "],["ind2"," "]])
        out.writeTag("subfield","INDICO.%s" % recId,[["code","a"]])
        out.closeTag("datafield")

        out.openTag("datafield",[["tag","980"],["ind1"," "],["ind2"," "]])
        out.writeTag("subfield","DELETED",[["code","c"]])
        out.closeTag("datafield")

        out.closeTag("record")

    def generateResourceAdded(self, obj, out=None):
        if not out:
            out = self._XMLGen
        if isinstance(obj,conference.Resource):
            if obj.canAccess(self._user):
                self._resourceAddedToMarc(obj, out)
        else:
            raise Exception("unknown object type: %s" % obj.__class__)

    def _resourceAddedToMarc(self, obj, out):

        out.openTag("record")

        out.openTag("datafield",[["tag","980"],["ind1"," "],["ind2"," "]])
        out.writeTag("subfield","ADD_RESOURCE",[["code","c"]])
        out.closeTag("datafield")

        out.openTag("datafield",[["tag","970"],["ind1"," "],["ind2"," "]])
        out.writeTag("subfield","INDICO." + uniqueId(obj.getOwner().getOwner()),[["code","a"]])
        out.closeTag("datafield")

        self._outGen.resourceToXMLMarc21(obj, out)
        self._outGen._generateAccessList(obj, out)
        out.closeTag("record")

    def generateACLChanged(self, obj, out=None):
        if not out:
            out = self._XMLGen
        if not(isinstance(obj,conference.Conference) or isinstance(obj,conference.Contribution) \
                                                or isinstance(obj, conference.SubContribution)):
            raise Exception("unknown object type: %s" % obj.__class__)

        out.openTag("record")

        out.openTag("datafield",[["tag","970"],["ind1"," "],["ind2"," "]])
        out.writeTag("subfield","INDICO." + uniqueId(obj),[["code","a"]])
        out.closeTag("datafield")

        out.openTag("datafield",[["tag","980"],["ind1"," "],["ind2"," "]])
        out.writeTag("subfield", self._outGen._getRecordCollection(obj), [["code","a"]])
        out.writeTag("subfield","ACL",[["code","c"]])
        out.closeTag("datafield")

        self._outGen._generateAccessList(obj, out, specifyId=False)

        out.closeTag("record")

    def generateMovedChanged(self, obj, out=None):
        if not out:
            out = self._XMLGen
        if not(isinstance(obj,conference.Conference) or isinstance(obj,conference.Contribution) \
                                                or isinstance(obj, conference.SubContribution)):
            raise Exception("unknown object type: %s" % obj.__class__)

        out.openTag("record")

        out.openTag("datafield",[["tag","970"],["ind1"," "],["ind2"," "]])
        out.writeTag("subfield","INDICO." + uniqueId(obj),[["code","a"]])
        out.closeTag("datafield")

        out.openTag("datafield",[["tag","980"],["ind1"," "],["ind2"," "]])
        out.writeTag("subfield", self._outGen._getRecordCollection(obj), [["code","a"]])
        out.writeTag("subfield","CATEGORY",[["code","c"]])
        out.closeTag("datafield")

        for path in obj.getConference().getCategoriesPath():
            out.openTag("datafield",[["tag","650"],["ind1"," "],["ind2","7"]])
            out.writeTag("subfield", ":".join(path), [["code","a"]])
            out.writeTag("subfield", "/".join(conference.CategoryManager().getById(categId).getTitle() for categId in path), [["code","e"]])
            out.closeTag("datafield")

        out.closeTag("record")

    def generate(self, obj, out=None, overrideCache=False, includeIndicator=False):
        if not out:
            out = self._XMLGen

        if isinstance(obj, conference.Conference):
            self.confToXMLMarc(obj, out=out, overrideCache=overrideCache, includeIndicator=includeIndicator)
        elif isinstance(obj, conference.Contribution):
            self.contToXMLMarc(obj, out=out, overrideCache=overrideCache, includeIndicator=includeIndicator)
        elif isinstance(obj, conference.SubContribution):
            self.subContToXMLMarc(obj, out=out, overrideCache=overrideCache, includeIndicator=includeIndicator)
        else:
            raise Exception("unknown object type: %s" % obj.__class__)

    def confToXMLMarc(self, obj, out=None, overrideCache=False, includeIndicator=False):
        if not out:
            out = self._XMLGen
        out.openTag("record")
        self._outGen.confToXMLMarc21(obj, out=out, overrideCache=overrideCache, includeIndicator=includeIndicator)
        out.closeTag("record")

    def sessionToXMLMarc(self, obj, out=None, overrideCache=False, includeIndicator=False):
        if not out:
            out = self._XMLGen
        out.openTag("record")
        self._outGen.sessionToXMLMarc21(obj, out=out, overrideCache=overrideCache, includeIndicator=includeIndicator)
        out.closeTag("record")

    def contToXMLMarc(self, obj, out=None, overrideCache=False, includeIndicator=False):
        if not out:
            out = self._XMLGen
        out.openTag("record")
        self._outGen.contribToXMLMarc21(obj, out=out, overrideCache=overrideCache, includeIndicator=includeIndicator)
        out.closeTag("record")

    def subContToXMLMarc(self, obj, out=None, overrideCache=False, includeIndicator=False):
        if not out:
            out = self._XMLGen
        out.openTag("record")
        self._outGen.subContribToXMLMarc21(obj, out=out, overrideCache=overrideCache, includeIndicator=includeIndicator)
        out.closeTag("record")
