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

"""
Agent definitions for CERN Search
"""

# standard library imports
import time, base64
from urllib2 import urlopen, Request, HTTPError
from urllib import urlencode

# dependency imports
from lxml import etree

# plugin imports
from indico.ext.livesync.agent import AgentProviderComponent, RecordUploader
from indico.ext.livesync.batch import (BaseBatchUploaderAgent, BaseRecordProcessor, STATUS_DELETED, STATUS_CHANGED,
    STATUS_CREATED, STATUS_ACL_CHANGED, STATUS_MOVED, STATUS_RESOURCE_ADDED, STATUS_RESOURCE_DELETED)
from indico.ext.livesync.metadata import MARCXMLGenerator
from indico.util.date_time import nowutc
from MaKaC.common.xmlGen import XMLGen
from MaKaC import conference


class CERNSearchRecordProcessor(BaseRecordProcessor):

    @classmethod
    def computeRecords(cls, data, access, dbi=None):
        """
        Receives a sequence of ActionWrappers and returns a sequence
        of records to be updated (created, changed or deleted)
        """

        records = dict()
        deletedIds = dict()

        for __, aw in data:
            obj = aw.getObject()

            ## TODO: enable this, when config is possible from interface
            ## if not obj.canAccess(AccessWrapper(access)):
            ##     # no access? jump over this one
            ##     continue
            for action in aw.getActions():
                if action == 'deleted' and not isinstance(obj, conference.Category):
                    # if the record has been deleted, mark it as such
                    # nothing else will matter
                    deletedIds[obj] = aw.getObjectId()
                    cls._setStatus(records, obj, STATUS_DELETED)

                elif action == 'created' and not isinstance(obj, conference.Category):
                    # if the record has been created, mark it as such
                    cls._setStatus(records, obj, STATUS_CREATED)

                # protection changes have to be handled more carefully
                elif action in ['set_private', 'set_public', 'acl_changed']:
                    cls._computeProtectionChanges(obj, action, records, STATUS_ACL_CHANGED, dbi=dbi, checkInheritance=True)
                elif action =='moved':
                    cls._computeProtectionChanges(obj, action, records, STATUS_MOVED, dbi=dbi)
                elif action == 'data_changed':
                    if not isinstance(obj, conference.Category):
                        cls._setStatus(records, obj, STATUS_CHANGED)
                elif action == "title_changed" and isinstance(obj, conference.Category):
                    cls._computeProtectionChanges(obj, action, records, STATUS_MOVED, dbi=dbi)
                elif action == 'resource_added':
                    cls._setStatus(records, obj, STATUS_RESOURCE_ADDED)
                elif action == 'resource_deleted':
                    cls._setStatus(records, obj, STATUS_RESOURCE_DELETED)
        for robj, state in records.iteritems():
            if state & STATUS_DELETED:
                yield robj, deletedIds[robj], state
            else:
                yield robj, None, state


class CERNSearchUploadAgent(BaseBatchUploaderAgent):

    _extraOptions = {'url': 'Server URL',
                     'username': 'Username',
                     'password': 'Password'}

    def __init__(self, aid, name, description, updateTime,
                 access=None, url=None, username=None, password=None):
        super(CERNSearchUploadAgent, self).__init__(
            aid, name, description, updateTime, access)
        self._url = url
        self._username = username
        self._password = password

    def _run(self, records, logger=None, monitor=None, dbi=None, task=None):

        self._v_logger = logger

        # the uploader will manage everything for us...
        uploader = CERNSearchRecordUploader(logger, self, self._url,
                                            self._username, self._password, task)
        if self._v_logger:
            self._v_logger.info('Starting metadata/upload cycle')

        # iterate over the returned records and upload them
        return uploader.iterateOver(records, dbi=dbi)

    def _getMetadata(self, records, logger=None):
        """
        Retrieves the MARCXML metadata for the record
        """
        xg = XMLGen()
        mg = MARCXMLGenerator(xg)
        # set the permissions
        mg.setPermissionsOf(self._access)

        xg.initXml()
        xg.openTag("collection", [["xmlns", "http://www.loc.gov/MARC21/slim"]])

        for record, recId, operation in records:
            try:
                if operation & STATUS_DELETED:
                    mg.generateDeleted(recId)
                else:
                    if record.getOwner():
                        if operation & STATUS_CREATED or operation & STATUS_CHANGED or operation & STATUS_RESOURCE_DELETED:
                            mg.generate(record, overrideCache=True, includeIndicator= bool(operation & STATUS_CHANGED))
                        if operation & STATUS_ACL_CHANGED:
                            mg.generateACLChanged(record)
                        if operation & STATUS_MOVED:
                            mg.generateMovedChanged(record)
                        if operation & STATUS_RESOURCE_ADDED:
                            mg.generateResourceAdded(record)

                    else:
                        logger.warning('%s (%s) is marked as non-deleted and has no owner' % \
                                       (record, recId))
            except:
                if logger:
                    logger.exception("Something went wrong while processing '%s' (recId=%s) (owner=%s)! Possible metadata errors." %
                                     (record, recId, record.getOwner()))
                    # avoid duplicate record
                self._removeUnfinishedRecord(mg._XMLGen)

        xg.closeTag("collection")

        return xg.getXml()

    def _generateRecords(self, data, lastTS, dbi=None):
        return CERNSearchRecordProcessor.computeRecords(data, self._access, dbi=dbi)


class CERNSearchRecordUploader(RecordUploader):
    """
    A worker that uploads data using HTTP
    """

    def __init__(self, logger, agent, url, username, password, task=None):
        super(CERNSearchRecordUploader, self).__init__(logger, agent)
        self._url = url
        self._username = username
        self._password = password
        self._task = task

    def _postRequest(self, batch):

        pass

    def _uploadBatch(self, batch):
        """
        Uploads a batch to the server
        """

        url = "%s/ImportXML" % self._url

        self._logger.debug('getting a batch')

        tstart = time.time()
        # get a batch

        self._logger.info('Generating metadata')
        data = self._agent._getMetadata(batch, logger=self._logger)
        self._logger.info('Metadata ready ')

        postData = {
            'xml': data
            }

        tgen = time.time() - tstart

        req = Request(url)
        # remove line break
        cred = base64.encodestring(
            '%s:%s' % (self._username, self._password)).strip()

        req.add_header("Authorization", "Basic %s" % cred)

        try:
            result = urlopen(req, data=urlencode(postData))
        except HTTPError, e:
            self._logger.exception("Status %s: \n %s" % (e.code, e.read()))
            raise Exception('upload failed')

        result_data = result.read()

        tupload = time.time() - (tstart + tgen)

        self._logger.debug('rec %s result: %s' % (batch, result_data))

        xmlDoc = etree.fromstring(result_data)

        # right now there is nothing else to pay attention to
        booleanResult = etree.tostring(xmlDoc, method="text")

        if self._task:
            self._task.setOnRunningListSince(nowutc())

        if result.code == 200 and booleanResult == 'true':
            self._logger.info('Batch of %d records stored in server'
                              ' [%f s %f s]' % \
                              (len(batch), tgen, tupload))
        else:
            self._logger.error('Records: %s output: %s '
                               '(HTTP code %s)' % (batch, result_data, result.code))
            raise Exception('upload failed')

        return True


class CERNSearchAgentProviderComponent(AgentProviderComponent):
    _agentType = CERNSearchUploadAgent
