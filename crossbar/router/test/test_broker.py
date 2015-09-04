#####################################################################################
#
#  Copyright (C) Tavendo GmbH
#
#  Unless a separate license agreement exists between you and Tavendo GmbH (e.g. you
#  have purchased a commercial license), the license terms below apply.
#
#  Should you enter into a separate license agreement after having received a copy of
#  this software, then the terms of such license agreement replace the terms below at
#  the time at which such license agreement becomes effective.
#
#  In case a separate license agreement ends, and such agreement ends without being
#  replaced by another separate license agreement, the license terms below apply
#  from the time at which said agreement ends.
#
#  LICENSE TERMS
#
#  This program is free software: you can redistribute it and/or modify it under the
#  terms of the GNU Affero General Public License, version 3, as published by the
#  Free Software Foundation. This program is distributed in the hope that it will be
#  useful, but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
#  See the GNU Affero General Public License Version 3 for more details.
#
#  You should have received a copy of the GNU Affero General Public license along
#  with this program. If not, see <http://www.gnu.org/licenses/agpl-3.0.en.html>.
#
#####################################################################################

from __future__ import absolute_import

from twisted.trial import unittest

import txaio
import mock

from autobahn.wamp import types
from autobahn.wamp import message
from autobahn.wamp import role
from autobahn.twisted.wamp import ApplicationSession

from crossbar.router.service import RouterServiceSession
from crossbar.worker.router import RouterRealm
from crossbar.router.router import RouterFactory
from crossbar.router.session import RouterSessionFactory
from crossbar.router.broker import Broker
from crossbar.router.role import RouterRoleStaticAuth, RouterPermissions


class TestBrokerPublish(unittest.TestCase):
    """
    Test cases for application session running embedded in router.
    """

    def setUp(self):
        """
        Setup router and router session factories.
        """

        # create a router factory
        self.router_factory = RouterFactory()

        # start a realm
        self.realm = RouterRealm(None, {u'name': u'realm1'})
        self.router_factory.start_realm(self.realm)

        # allow everything
        permissions = RouterPermissions('', True, True, True, True, True)
        self.router = self.router_factory.get(u'realm1')
        self.router.add_role(RouterRoleStaticAuth(self.router, None, default_permissions=permissions))

        # create a router session factory
        self.session_factory = RouterSessionFactory(self.router_factory)

    def tearDown(self):
        pass

    def test_add(self):
        """
        Create an application session and add it to a router to
        run embedded.
        """
        d = txaio.create_future()

        class TestSession(ApplicationSession):

            def onJoin(self, details):
                txaio.resolve(d, None)

        session = TestSession(types.ComponentConfig(u'realm1'))

        self.session_factory.add(session)

        return d

    def _test_application_session_internal_error(self):
        """
        simulate an internal error triggering the 'onJoin' error-case from
        _RouterApplicationSession's send() method (from the Hello msg)
        """
        # setup
        the_exception = RuntimeError("sadness")

        class TestSession(ApplicationSession):
            def onJoin(self, *args, **kw):
                raise the_exception
        session = TestSession(types.ComponentConfig(u'realm1'))
        from crossbar.router.session import _RouterApplicationSession

        # execute, first patching-out the logger so we can see that
        # log.failure() was called when our exception triggers.
        with mock.patch.object(_RouterApplicationSession, 'log') as logger:
            # this should call onJoin, triggering our error
            self.session_factory.add(session)

            # check we got the right log.failure() call
            self.assertTrue(len(logger.method_calls) > 0)
            call = logger.method_calls[0]
            # for a MagicMock call-object, 0th thing is the method-name, 1st
            # thing is the arg-tuple, 2nd thing is the kwargs.
            self.assertEqual(call[0], 'failure')
            self.assertTrue('failure' in call[2])
            self.assertEqual(call[2]['failure'].value, the_exception)

    def test_router_session_internal_error_onHello(self):
        """
        similar to above, but during _RouterSession's onMessage handling,
        where it calls self.onHello
        """
        # setup
        transport = mock.MagicMock()
        the_exception = RuntimeError("kerblam")

        def boom(*args, **kw):
            raise the_exception
        session = self.session_factory()  # __call__ on the _RouterSessionFactory
        session.onHello = boom
        session.onOpen(transport)
        msg = message.Hello(u'realm1', dict(caller=role.RoleCallerFeatures()))

        # XXX think: why isn't this using _RouterSession.log?
        from crossbar.router.session import RouterSession
        with mock.patch.object(RouterSession, 'log') as logger:
            # do the test; should call onHello which is now "boom", above
            session.onMessage(msg)

            # check we got the right log.failure() call
            self.assertTrue(len(logger.method_calls) > 0)
            call = logger.method_calls[0]
            # for a MagicMock call-object, 0th thing is the method-name, 1st
            # thing is the arg-tuple, 2nd thing is the kwargs.
            self.assertEqual(call[0], 'failure')
            self.assertTrue('failure' in call[2])
            self.assertEqual(call[2]['failure'].value, the_exception)

    def test_router_session_internal_error_onAuthenticate(self):
        """
        similar to above, but during _RouterSession's onMessage handling,
        where it calls self.onAuthenticate)
        """
        # setup
        transport = mock.MagicMock()
        the_exception = RuntimeError("kerblam")

        def boom(*args, **kw):
            raise the_exception
        session = self.session_factory()  # __call__ on the _RouterSessionFactory
        session.onAuthenticate = boom
        session.onOpen(transport)
        msg = message.Authenticate(u'bogus signature')

        # XXX think: why isn't this using _RouterSession.log?
        from crossbar.router.session import RouterSession
        with mock.patch.object(RouterSession, 'log') as logger:
            # do the test; should call onHello which is now "boom", above
            session.onMessage(msg)

            # check we got the right log.failure() call
            self.assertTrue(len(logger.method_calls) > 0)
            call = logger.method_calls[0]
            # for a MagicMock call-object, 0th thing is the method-name, 1st
            # thing is the arg-tuple, 2nd thing is the kwargs.
            self.assertEqual(call[0], 'failure')
            self.assertTrue('failure' in call[2])
            self.assertEqual(call[2]['failure'].value, the_exception)

    def test_add_and_subscribe(self):
        """
        Create an application session that subscribes to some
        topic and add it to a router to run embedded.
        """
        d = txaio.create_future()

        class TestSession(ApplicationSession):

            def onJoin(self, details):
                # noinspection PyUnusedLocal
                def on_event(*arg, **kwargs):
                    pass

                d2 = self.subscribe(on_event, u'com.example.topic1')

                def ok(_):
                    txaio.resolve(d, None)

                def error(err):
                    txaio.reject(d, err)

                txaio.add_callbacks(d2, ok, error)

        session = TestSession(types.ComponentConfig(u'realm1'))

        self.session_factory.add(session)

        return d

    def test_publish_closed_session(self):
        """
        ensure a session doesn't get Events if it's closed
        (see also issue #431)
        """
        # we want to trigger a deeply-nested condition in
        # processPublish in class Broker -- lets try w/o refactoring
        # anything first...

        class TestSession(ApplicationSession):
            pass
        session0 = TestSession()
        session1 = TestSession()
        router = mock.MagicMock()
        broker = Broker(router)

        # let's just "cheat" our way a little to the right state by
        # injecting our subscription "directly" (e.g. instead of
        # faking out an entire Subscribe etc. flow
        # ...so we need _subscriptions_map to have at least one
        # subscription (our test one) for the topic we'll publish to
        broker._subscription_map.add_observer(session0, u'test.topic')

        # simulate the session state we want, which is that a
        # transport is connected (._transport != None) but there
        # _session_id *is* None (not joined yet, or left already)
        self.assertIs(None, session0._session_id)
        session0._transport = mock.MagicMock()
        session1._session_id = 1234  # "from" session should look connected + joined
        session1._transport = mock.MagicMock()

        # here's the main "cheat"; we're faking out the
        # router.authorize because we need it to callback immediately
        router.authorize = mock.MagicMock(return_value=txaio.create_future_success(True))

        # now we scan call "processPublish" such that we get to the
        # condition we're interested in (this "comes from" session1
        # beacuse by default publishes don't go to the same session)
        pubmsg = message.Publish(123, u'test.topic')
        broker.processPublish(session1, pubmsg)

        # neither session should have sent anything on its transport
        self.assertEquals(session0._transport.method_calls, [])
        self.assertEquals(session1._transport.method_calls, [])
