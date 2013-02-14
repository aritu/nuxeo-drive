import os
import time
import urllib2
import socket
import httplib
from datetime import datetime

from nxdrive.tests.common import IntegrationTestCase
from nxdrive.client import LocalClient
from nxdrive.model import LastKnownState


class TestIntegrationSynchronization(IntegrationTestCase):

    def test_binding_initialization_and_first_sync(self):
        ctl = self.controller_1
        # Create some documents in a Nuxeo workspace and bind this server to a
        # Nuxeo Drive local folder
        self.make_server_tree()
        ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        ctl.bind_root(self.local_nxdrive_folder_1, self.workspace)
        syn = ctl.synchronizer

        # The root binding operation does not create the local folder 
        # yet.
        expected_folder = os.path.join(self.local_nxdrive_folder_1,
                                       self.workspace_title)
        local_client = LocalClient(self.local_nxdrive_folder_1)
        self.assertFalse(local_client.exists('/' + self.workspace_title))

        # By default only scan happen, hence their is no information on the state
        # of the documents on the local side (they don't exist there yet)
        states = ctl.children_states(expected_folder)
        self.assertEquals(states, [])

        # Only the root binding is stored in the DB
        self.assertEquals(len(self.get_all_states()), 1)

        # Trigger some scan manually
        syn.scan_local(self.local_nxdrive_folder_1)
        syn.scan_remote(self.local_nxdrive_folder_1)

        # Check the list of files and folders with synchronization pending
        pending = ctl.list_pending()
        self.assertEquals(len(pending), 12)
        remote_names = [p.remote_name for p in pending]
        remote_names.sort()
        self.assertEquals(remote_names, [
            u'Duplicated File.txt',
            u'Duplicated File.txt',
            u'File 1.txt',
            u'File 2.txt',
            u'File 3.txt',
            u'File 4.txt',
            u'File 5.txt',
            u'Folder 1',
            u'Folder 1.1',
            u'Folder 1.2',
            u'Folder 2',
            u'Nuxeo Drive Test Workspace',
        ])

        # It is also possible to restrict the list of pending document to a
        # specific server binding
        self.assertEquals(len(ctl.list_pending(
                          local_folder=self.local_nxdrive_folder_1)), 12)

        # It is also possible to restrict the number of pending tasks
        pending = ctl.list_pending(limit=2)
        self.assertEquals(len(pending), 2)

        # Synchronize the first document (ordered by hierarchy):
        self.assertEquals(syn.synchronize(
            self.local_nxdrive_folder_1, limit=1), 1)
        pending = ctl.list_pending()
        self.assertEquals(len(pending), 11)
        remote_names = [p.remote_name for p in pending]
        remote_names.sort()
        self.assertEquals(remote_names, [
            u'Duplicated File.txt',
            u'Duplicated File.txt',
            u'File 1.txt',
            u'File 2.txt',
            u'File 3.txt',
            u'File 4.txt',
            u'File 5.txt',
            u'Folder 1',
            u'Folder 1.1',
            u'Folder 1.2',
            u'Folder 2',
        ])
        states = ctl.children_states(self.local_nxdrive_folder_1)
        self.assertEquals(states, [
            (u'Nuxeo Drive Test Workspace', u'children_modified'),
        ])

        # The workspace folder is still unknown from the client point
        # of view
        states = ctl.children_states(expected_folder)
        self.assertEquals(states, [])

        # synchronize everything else
        self.assertEquals(syn.synchronize(), 11)
        self.assertEquals(ctl.list_pending(), [])
        states = ctl.children_states(expected_folder)
        expected_states = [
            (u'File 5.txt', 'synchronized'),
            (u'Folder 1', 'synchronized'),
            (u'Folder 2', 'synchronized'),
        ]
        self.assertEquals(states, expected_states)

        # The actual content of the file has been updated
        file_5_content = local_client.get_content(
            '/Nuxeo Drive Test Workspace/File 5.txt')
        self.assertEquals(file_5_content, "eee")

        states = ctl.children_states(expected_folder + '/Folder 1')
        expected_states = [
            (u'File 1.txt', 'synchronized'),
            (u'Folder 1.1', 'synchronized'),
            (u'Folder 1.2', 'synchronized'),
        ]
        self.assertEquals(states, expected_states)
        self.assertEquals(local_client.get_content(
            '/Nuxeo Drive Test Workspace/Folder 1/File 1.txt'),
            "aaa")

        self.assertEquals(local_client.get_content(
            '/Nuxeo Drive Test Workspace/Folder 1/Folder 1.1/File 2.txt'),
            "bbb")

        self.assertEquals(local_client.get_content(
            '/Nuxeo Drive Test Workspace/Folder 1/Folder 1.2/File 3.txt'),
            "ccc")

        self.assertEquals(local_client.get_content(
            '/Nuxeo Drive Test Workspace/Folder 2/File 4.txt'),
            "ddd")

        c1 = local_client.get_content(
            '/Nuxeo Drive Test Workspace/Folder 2/Duplicated File.txt')

        c2 = local_client.get_content(
            '/Nuxeo Drive Test Workspace/Folder 2/Duplicated File__1.txt')

        self.assertEquals(tuple(sorted((c1, c2))),
                          ("Other content.", "Some content."))

        # Nothing else left to synchronize
        self.assertEquals(ctl.list_pending(), [])
        self.assertEquals(syn.synchronize(), 0)
        self.assertEquals(ctl.list_pending(), [])

        # Unbind root and resynchronize: smoke test
        ctl.unbind_root(self.local_nxdrive_folder_1, self.workspace)
        self.assertEquals(ctl.list_pending(), [])
        self.assertEquals(syn.synchronize(), 0)
        self.assertEquals(ctl.list_pending(), [])

    def test_binding_synchronization_empty_start(self):
        ctl = self.controller_1
        remote_client = self.remote_document_client_1
        ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        ctl.bind_root(self.local_nxdrive_folder_1, self.workspace)
        syn = ctl.synchronizer
        expected_folder = os.path.join(self.local_nxdrive_folder_1,
                                       self.workspace_title)

        # Nothing to synchronize by default
        self.assertEquals(ctl.list_pending(), [])
        self.assertEquals(syn.synchronize(), 0)

        # Let's create some document on the server
        self.make_server_tree()

        # By default nothing is detected
        self.assertEquals(ctl.list_pending(), [])
        self.assertEquals(ctl.children_states(expected_folder), [])

        # Let's scan manually
        syn.scan_remote(self.local_nxdrive_folder_1)

        # Changes on the remote server have been detected...
        self.assertEquals(len(ctl.list_pending()), 12)

        # ...but nothing is yet visible locally as those files don't exist
        # there yet.
        self.assertEquals(ctl.children_states(expected_folder), [])

        # Let's perform the synchronization
        self.assertEquals(syn.synchronize(limit=100), 12)

        # We should now be fully synchronized
        self.assertEquals(len(ctl.list_pending()), 0)
        self.assertEquals(ctl.children_states(expected_folder), [
            (u'File 5.txt', u'synchronized'),
            (u'Folder 1', u'synchronized'),
            (u'Folder 2', u'synchronized'),
        ])
        local_client = LocalClient(self.local_nxdrive_folder_1)
        self.assertEquals(local_client.get_content(
            '/Nuxeo Drive Test Workspace/Folder 1/File 1.txt'),
            "aaa")

        self.assertEquals(local_client.get_content(
            '/Nuxeo Drive Test Workspace/Folder 1/Folder 1.1/File 2.txt'),
            "bbb")

        self.assertEquals(local_client.get_content(
            '/Nuxeo Drive Test Workspace/Folder 1/Folder 1.2/File 3.txt'),
            "ccc")

        self.assertEquals(local_client.get_content(
            '/Nuxeo Drive Test Workspace/Folder 2/File 4.txt'),
            "ddd")

        c1 = local_client.get_content(
            '/Nuxeo Drive Test Workspace/Folder 2/Duplicated File.txt')

        c2 = local_client.get_content(
            '/Nuxeo Drive Test Workspace/Folder 2/Duplicated File__1.txt')

        self.assertEquals(tuple(sorted((c1, c2))),
                          ("Other content.", "Some content."))

        # Wait a bit for file time stamps to increase enough: on most OS the
        # file modification time resolution is 1s
        time.sleep(1.0)

        # Let do some local and remote changes concurrently
        local_client.delete('/Nuxeo Drive Test Workspace/File 5.txt')
        local_client.update_content(
            '/Nuxeo Drive Test Workspace/Folder 1/File 1.txt', 'aaaa')

        # The remote client use in this test is handling paths relative to
        # the 'Nuxeo Drive Test Workspace'
        remote_client.update_content('/Folder 1/Folder 1.1/File 2.txt',
                                     'bbbb')
        remote_client.delete('/Folder 2')
        f3 = remote_client.make_folder(self.workspace, 'Folder 3')
        remote_client.make_file(f3, 'File 6.txt', content='ffff')
        local_client.make_folder('/Nuxeo Drive Test Workspace', 'Folder 4')

        # Rescan
        syn.scan_local(self.local_nxdrive_folder_1)
        syn.scan_remote(self.local_nxdrive_folder_1)
        self.assertEquals(ctl.children_states(expected_folder), [
            (u'File 5.txt', u'locally_deleted'),
            (u'Folder 1', u'children_modified'),
            (u'Folder 2', u'children_modified'),  # what do we want for this?
            # Folder 3 is not yet visible has not sync has happen to give it a
            # local path yet
            (u'Folder 4', u'unknown'),
        ])
        # The information on the remote state of Folder 3 has been stored in
        # the database though
        session = ctl.get_session()
        f3_state = session.query(LastKnownState).filter_by(
            remote_name='Folder 3').one()
        self.assertEquals(f3_state.local_path, None)

        states = ctl.children_states(expected_folder + '/Folder 1')
        expected_states = [
            (u'File 1.txt', 'locally_modified'),
            (u'Folder 1.1', 'children_modified'),
            (u'Folder 1.2', 'synchronized'),
        ]
        self.assertEquals(states, expected_states)
        states = ctl.children_states(expected_folder + '/Folder 1/Folder 1.1')
        expected_states = [
            (u'File 2.txt', u'remotely_modified'),
        ]
        self.assertEquals(states, expected_states)
        states = ctl.children_states(expected_folder + '/Folder 2')
        expected_states = [
            (u'Duplicated File.txt', u'remotely_deleted'),
            (u'Duplicated File__1.txt', u'remotely_deleted'),
            (u'File 4.txt', u'remotely_deleted'),
        ]
        self.assertEquals(states, expected_states)

        # Perform synchronization
        self.assertEquals(syn.synchronize(limit=100), 10)

        # We should now be fully synchronized again
        self.assertEquals(len(ctl.list_pending()), 0)
        self.assertEquals(ctl.children_states(expected_folder), [
            (u'Folder 1', 'synchronized'),
            (u'Folder 3', 'synchronized'),
            (u'Folder 4', 'synchronized'),
        ])
        states = ctl.children_states(expected_folder + '/Folder 1')
        expected_states = [
            (u'File 1.txt', 'synchronized'),
            (u'Folder 1.1', 'synchronized'),
            (u'Folder 1.2', 'synchronized'),
        ]
        self.assertEquals(states, expected_states)
        local = LocalClient(expected_folder)
        self.assertEquals(local.get_content(
            '/Folder 1/File 1.txt'),
            "aaaa")
        self.assertEquals(local.get_content(
            '/Folder 1/Folder 1.1/File 2.txt'),
            "bbbb")
        self.assertEquals(local.get_content(
            '/Folder 3/File 6.txt'),
            "ffff")
        self.assertEquals(remote_client.get_content(
            '/Folder 1/File 1.txt'),
            "aaaa")
        self.assertEquals(remote_client.get_content(
            '/Folder 1/Folder 1.1/File 2.txt'),
            "bbbb")
        self.assertEquals(remote_client.get_content(
            '/Folder 3/File 6.txt'),
            "ffff")

        # Rescan: no change to detect we should reach a fixpoint
        syn.scan_local(self.local_nxdrive_folder_1)
        syn.scan_remote(self.local_nxdrive_folder_1)
        self.assertEquals(len(ctl.list_pending()), 0)
        self.assertEquals(ctl.children_states(expected_folder), [
            (u'Folder 1', 'synchronized'),
            (u'Folder 3', 'synchronized'),
            (u'Folder 4', 'synchronized'),
        ])

        # Send some binary data that is not valid in utf-8 or ascii (to test the
        # HTTP / Multipart transform layer).
        time.sleep(1.0)
        local.update_content('/Folder 1/File 1.txt', "\x80")
        remote_client.update_content('/Folder 1/Folder 1.1/File 2.txt', '\x80')
        syn.scan_local(self.local_nxdrive_folder_1)
        syn.scan_remote(self.local_nxdrive_folder_1)
        self.assertEquals(syn.synchronize(limit=100), 2)
        self.assertEquals(remote_client.get_content('/Folder 1/File 1.txt'), "\x80")
        self.assertEquals(local.get_content('/Folder 1/Folder 1.1/File 2.txt'), "\x80")

    def test_synchronization_modification_on_created_file(self):
        ctl = self.controller_1
        # Regression test: a file is created locally, then modification is detected
        # before first upload
        ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        ctl.bind_root(self.local_nxdrive_folder_1, self.workspace)
        syn = ctl.synchronizer
        expected_folder = os.path.join(self.local_nxdrive_folder_1,
                                       self.workspace_title)
        self.assertEquals(ctl.list_pending(), [])

        # Let's create some document on the client and the server
        local = LocalClient(expected_folder)
        local.make_folder('/', 'Folder')
        local.make_file('/Folder', 'File.txt', content='Some content.')

        # First local scan (assuming the network is offline):
        syn.scan_local(expected_folder)
        self.assertEquals(len(ctl.list_pending()), 2)
        self.assertEquals(ctl.children_states(expected_folder), [
            (u'Folder', 'children_modified'),
        ])
        self.assertEquals(ctl.children_states(expected_folder + '/Folder'), [
            (u'File.txt', u'unknown'),
        ])

        # Wait a bit for file time stamps to increase enough: on most OS the file
        # modification time resolution is 1s
        time.sleep(1.0)

        # Let's modify it offline and rescan locally
        local.update_content('/Folder/File.txt', content='Some content.')
        syn.scan_local(expected_folder)
        self.assertEquals(len(ctl.list_pending()), 2)
        self.assertEquals(ctl.children_states(expected_folder), [
            (u'Folder', u'children_modified'),
        ])
        self.assertEquals(ctl.children_states(expected_folder + '/Folder'), [
            (u'File.txt', u'locally_modified'),
        ])

        # Assume the computer is back online, the synchronization should occur as if
        # the document was just created and not trigger an update
        self.wait()
        syn.loop(delay=0.010, max_loops=1)
        self.assertEquals(len(ctl.list_pending()), 0)
        self.assertEquals(ctl.children_states(expected_folder), [
            (u'Folder', u'synchronized'),
        ])
        self.assertEquals(ctl.children_states(expected_folder + '/Folder'), [
            (u'File.txt', u'synchronized'),
        ])

    def test_synchronization_loop(self):
        ctl = self.controller_1
        ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        ctl.bind_root(self.local_nxdrive_folder_1, self.workspace)
        syn = ctl.synchronizer
        expected_folder = os.path.join(self.local_nxdrive_folder_1,
                                       self.workspace_title)

        self.assertEquals(ctl.list_pending(), [])
        self.assertEquals(syn.synchronize(), 0)

        # Let's create some document on the client and the server
        local = LocalClient(expected_folder)
        local.make_folder('/', 'Folder 3')
        self.make_server_tree()

        # Run the full synchronization loop a limited amount of times
        self.wait()
        syn.loop(delay=0.010, max_loops=3)

        # All is synchronized
        self.assertEquals(len(ctl.list_pending()), 0)
        self.assertEquals(ctl.children_states(expected_folder), [
            (u'File 5.txt', u'synchronized'),
            (u'Folder 1', u'synchronized'),
            (u'Folder 2', u'synchronized'),
            (u'Folder 3', u'synchronized'),
        ])

    def test_synchronization_loop_skip_errors(self):
        ctl = self.controller_1
        ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        ctl.bind_root(self.local_nxdrive_folder_1, self.workspace)
        syn = ctl.synchronizer
        expected_folder = os.path.join(self.local_nxdrive_folder_1,
                                       self.workspace_title)

        self.assertEquals(ctl.list_pending(), [])
        self.assertEquals(syn.synchronize(), 0)

        # Let's create some document on the client and the server
        local = LocalClient(expected_folder)
        local.make_folder('/', 'Folder 3')
        self.make_server_tree()

        # Detect the files to synchronize but do not perform the
        # synchronization
        syn.scan_remote(expected_folder)
        syn.scan_local(expected_folder)
        pending = ctl.list_pending()
        self.assertEquals(len(pending), 12)
        self.assertEquals(pending[0].remote_name, 'File 5.txt')
        self.assertEquals(pending[0].pair_state, 'unknown')
        self.assertEquals(pending[1].remote_name, 'Folder 1')
        self.assertEquals(pending[1].pair_state, 'unknown')
        self.assertEquals(pending[11].local_name, 'Folder 3')
        self.assertEquals(pending[11].pair_state, 'unknown')

        # Simulate synchronization errors
        session = ctl.get_session()
        file_5 = session.query(LastKnownState).filter_by(
            remote_name='File 5.txt').one()
        file_5.last_sync_error_date = datetime.utcnow()
        folder_3 = session.query(LastKnownState).filter_by(
            local_name='Folder 3').one()
        folder_3.last_sync_error_date = datetime.utcnow()

        # Run the full synchronization loop a limited amount of times
        self.wait()
        syn.loop(delay=0, max_loops=3)

        # All errors have been skipped, while the remaining docs have
        # been synchronized
        pending = ctl.list_pending()
        self.assertEquals(len(pending), 2)
        self.assertEquals(pending[0].remote_name, 'File 5.txt')
        self.assertEquals(pending[0].pair_state, 'unknown')
        self.assertEquals(pending[1].local_name, 'Folder 3')
        self.assertEquals(pending[1].pair_state, 'unknown')

        # Reduce the skip delay to retry the sync on pairs in error
        syn.error_skip_period = 0.000001
        syn.loop(delay=0, max_loops=3)
        self.assertEquals(len(ctl.list_pending()), 0)
        self.assertEquals(ctl.children_states(expected_folder), [
            (u'File 5.txt', u'synchronized'),
            (u'Folder 1', u'synchronized'),
            (u'Folder 2', u'synchronized'),
            (u'Folder 3', u'synchronized'),
        ])

    def test_synchronization_offline(self):
        ctl = self.controller_1
        ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        ctl.bind_root(self.local_nxdrive_folder_1, self.workspace)
        syn = ctl.synchronizer
        expected_folder = os.path.join(self.local_nxdrive_folder_1,
                                       self.workspace_title)

        self.assertEquals(ctl.list_pending(), [])
        self.assertEquals(syn.synchronize(), 0)

        # Let's create some document on the client and the server
        local = LocalClient(expected_folder)
        local.make_folder('/', 'Folder 3')
        self.make_server_tree()
        self.wait()

        # Find various ways to similate network or server failure
        errors = [
            urllib2.URLError('Test error'),
            socket.error('Test error'),
            httplib.HTTPException('Test error'),
        ]
        for error in errors:
            ctl.make_remote_raise(error)
            # Synchronization does not occur but does not fail either
            syn.loop(delay=0, max_loops=1)
            # Only the local change has been detected
            self.assertEquals(len(ctl.list_pending()), 1)

        # Reenable network
        ctl.make_remote_raise(None)
        syn.loop(delay=0, max_loops=1)

        # All is synchronized
        self.assertEquals(len(ctl.list_pending()), 0)
        self.assertEquals(ctl.children_states(expected_folder), [
            (u'File 5.txt', u'synchronized'),
            (u'Folder 1', u'synchronized'),
            (u'Folder 2', u'synchronized'),
            (u'Folder 3', u'synchronized'),
        ])

    def test_rebind_without_duplication(self):
        """Check that rebinding an existing folder will not duplicate everything"""
        ctl = self.controller_1
        ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        ctl.bind_root(self.local_nxdrive_folder_1, self.workspace)
        syn = ctl.synchronizer

        expected_folder = os.path.join(self.local_nxdrive_folder_1,
                                       self.workspace_title)

        self.assertEquals(ctl.list_pending(), [])

        # Let's create some document on the client and the server
        local = LocalClient(self.local_nxdrive_folder_1)
        local.make_folder('/', self.workspace_title)
        local.make_folder('/' + self.workspace_title, 'Folder 3')
        self.make_server_tree()
        self.wait()

        syn.loop(delay=0, max_loops=1)
        self.assertEquals(len(ctl.list_pending()), 0)

        self.assertEquals(self.get_all_states(), [
            (u'/', u'synchronized', u'synchronized'),
            (u'/File 5.txt', u'synchronized', u'synchronized'),
            (u'/Folder 1', u'synchronized', u'synchronized'),
            (u'/Folder 1/File 1.txt', u'synchronized', u'synchronized'),
            (u'/Folder 1/Folder 1.1', u'synchronized', u'synchronized'),
            (u'/Folder 1/Folder 1.1/File 2.txt', u'synchronized', u'synchronized'),
            (u'/Folder 1/Folder 1.2', u'synchronized', u'synchronized'),
            (u'/Folder 1/Folder 1.2/File 3.txt', u'synchronized', u'synchronized'),
            (u'/Folder 2', u'synchronized', u'synchronized'),
            (u'/Folder 2/Duplicated File.txt', u'synchronized', u'synchronized'),
            (u'/Folder 2/Duplicated File__1.txt', u'synchronized', u'synchronized'),
            (u'/Folder 2/File 4.txt', u'synchronized', u'synchronized'),
            (u'/Folder 3', u'synchronized', u'synchronized')
        ])
        self.assertEquals(len(local.get_children_info('/')), 4)

        # Unbind: the state database is emptied
        ctl.unbind_server(self.local_nxdrive_folder_1)
        self.assertEquals(self.get_all_states(), [])

        # Previously synchronized files are still there, untouched
        self.assertEquals(len(local.get_children_info('/')), 4)

        # Lets rebind the same folder to the same workspace
        ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        ctl.bind_root(self.local_nxdrive_folder_1, self.workspace)

        # Check that the bind that occurrs right after the bind automatically
        # detects the file alignments and hence everything is synchronized without
        self.assertEquals(len(ctl.list_pending()), 0)
        self.assertEquals(self.get_all_states(), [
            (u'/', u'synchronized', u'synchronized'),
            (u'/File 5.txt', u'synchronized', u'synchronized'),
            (u'/Folder 1', u'synchronized', u'synchronized'),
            (u'/Folder 1/File 1.txt', u'synchronized', u'synchronized'),
            (u'/Folder 1/Folder 1.1', u'synchronized', u'synchronized'),
            (u'/Folder 1/Folder 1.1/File 2.txt', u'synchronized', u'synchronized'),
            (u'/Folder 1/Folder 1.2', u'synchronized', u'synchronized'),
            (u'/Folder 1/Folder 1.2/File 3.txt', u'synchronized', u'synchronized'),
            (u'/Folder 2', u'synchronized', u'synchronized'),
            (u'/Folder 2/Duplicated File.txt', u'synchronized', u'synchronized'),
            (u'/Folder 2/Duplicated File__1.txt', u'synchronized', u'synchronized'),
            (u'/Folder 2/File 4.txt', u'synchronized', u'synchronized'),
            (u'/Folder 3', u'synchronized', u'synchronized')
        ])
        self.assertEquals(len(ctl.list_pending()), 0)
        self.assertEquals(len(local.get_children_info('/')), 4)
