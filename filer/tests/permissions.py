#-*- coding: utf-8 -*-
from __future__ import absolute_import

import os

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.files import File as DjangoFile
from django.test.testcases import TestCase

from .. import settings as filer_settings
from ..models.clipboardmodels import Clipboard
from ..models.foldermodels import Folder, FolderPermission
from ..settings import FILER_IMAGE_MODEL
from ..utils.loader import load_model
from .helpers import create_image, create_superuser
from .utils import Mock

Image = load_model(FILER_IMAGE_MODEL)


class FolderPermissionsTestCase(TestCase):

    def setUp(self):
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
        except ImportError:
            from django.contrib.auth.models import User  # NOQA
        self.superuser = create_superuser()
        self.client.login(username='admin', password='secret')

        self.unauth_user = User.objects.create(username='unauth_user')

        self.owner = User.objects.create(username='owner')

        self.test_user1 = User.objects.create(username='test1', password='secret')
        self.test_user2 = User.objects.create(username='test2', password='secret')
        self.test_user3 = User.objects.create(username='test3', password='secret')

        self.group1 = Group.objects.create(name='name1')
        self.group2 = Group.objects.create(name='name2')
        self.group3 = Group.objects.create(name='name3')
        self.group4 = Group.objects.create(name='name4')

        self.test_user1.groups.add(self.group1)
        self.test_user1.groups.add(self.group2)
        self.test_user2.groups.add(self.group3)
        self.test_user2.groups.add(self.group4)

        self.img = create_image()
        self.image_name = 'test_file.jpg'
        self.filename = os.path.join(settings.FILE_UPLOAD_TEMP_DIR, self.image_name)
        self.img.save(self.filename, 'JPEG')

        self.file = DjangoFile(open(self.filename, 'rb'), name=self.image_name)
        # This is actually a "file" for filer considerations
        self.image = Image.objects.create(owner=self.superuser,
                                     original_filename=self.image_name,
                                     file=self.file)
        self.clipboard = Clipboard.objects.create(user=self.superuser)
        self.clipboard.append_file(self.image)

        self.folder = Folder.objects.create(name='test_folder')

        self.folder_perm = Folder.objects.create(name='test_folder2')

    def tearDown(self):
        self.image.delete()

    def test_superuser_has_rights(self):
        request = Mock()
        setattr(request, 'user', self.superuser)

        result = self.folder.has_read_permission(request)
        self.assertEqual(result, True)

    def test_unlogged_user_has_no_rights(self):
        old_setting = filer_settings.FILER_ENABLE_PERMISSIONS
        try:
            filer_settings.FILER_ENABLE_PERMISSIONS = True
            request = Mock()
            setattr(request, 'user', self.unauth_user)

            result = self.folder.has_read_permission(request)
            self.assertEqual(result, False)
        finally:
            filer_settings.FILER_ENABLE_PERMISSIONS = old_setting

    def test_unlogged_user_has_rights_when_permissions_disabled(self):
        request = Mock()
        setattr(request, 'user', self.unauth_user)

        result = self.folder.has_read_permission(request)
        self.assertEqual(result, True)

    def test_owner_user_has_rights(self):
        # Set owner as the owner of the folder.
        self.folder.owner = self.owner
        request = Mock()
        setattr(request, 'user', self.owner)

        result = self.folder.has_read_permission(request)
        self.assertEqual(result, True)

    def test_combined_groups(self):
        request1 = Mock()
        setattr(request1, 'user', self.test_user1)
        request2 = Mock()
        setattr(request2, 'user', self.test_user2)

        old_setting = filer_settings.FILER_ENABLE_PERMISSIONS
        try:
            filer_settings.FILER_ENABLE_PERMISSIONS = True

            self.assertEqual(self.folder.has_read_permission(request1), False)
            self.assertEqual(self.folder.has_read_permission(request2), False)
            self.assertEqual(self.folder_perm.has_read_permission(request1), False)
            self.assertEqual(self.folder_perm.has_read_permission(request2), False)

            self.assertEqual(FolderPermission.objects.count(), 0)

            fp1 = FolderPermission.objects.create(folder=self.folder, type=FolderPermission.CHILDREN, can_edit=FolderPermission.DENY, can_read=FolderPermission.ALLOW, can_add_children=FolderPermission.DENY)
            fp2 = FolderPermission.objects.create(folder=self.folder_perm, type=FolderPermission.CHILDREN, can_edit=FolderPermission.DENY, can_read=FolderPermission.ALLOW, can_add_children=FolderPermission.DENY)
            fp1.groups.add(self.group1, self.group2)
            fp2.groups.add(self.group2, self.group3)

            self.assertEqual(FolderPermission.objects.count(), 2)

            # We have to invalidate cache
            delattr(self.folder, 'permission_cache')
            delattr(self.folder_perm, 'permission_cache')

            self.assertEqual(self.folder.has_read_permission(request1), True)
            self.assertEqual(self.folder.has_read_permission(request2), False)
            self.assertEqual(self.folder_perm.has_read_permission(request1), True)
            self.assertEqual(self.folder_perm.has_read_permission(request2), True)

            self.test_user2.groups.add(self.group1)

            # We have to invalidate cache
            delattr(self.folder, 'permission_cache')
            delattr(self.folder_perm, 'permission_cache')

            self.assertEqual(self.folder.has_read_permission(request1), True)
            self.assertEqual(self.folder.has_read_permission(request2), True)
            self.assertEqual(self.folder_perm.has_read_permission(request1), True)
            self.assertEqual(self.folder_perm.has_read_permission(request2), True)

        finally:
            filer_settings.FILER_ENABLE_PERMISSIONS = old_setting

    def test_overlapped_groups_deny1(self):
        # Tests overlapped groups with explicit deny

        request1 = Mock()
        setattr(request1, 'user', self.test_user1)

        old_setting = filer_settings.FILER_ENABLE_PERMISSIONS
        try:
            filer_settings.FILER_ENABLE_PERMISSIONS = True

            self.assertEqual(self.folder.has_read_permission(request1), False)
            self.assertEqual(self.folder_perm.has_read_permission(request1), False)

            self.assertEqual(FolderPermission.objects.count(), 0)

            fp1 = FolderPermission.objects.create(folder=self.folder, type=FolderPermission.CHILDREN, can_edit=FolderPermission.DENY, can_read=FolderPermission.ALLOW, can_add_children=FolderPermission.DENY)
            fp2 = FolderPermission.objects.create(folder=self.folder, type=FolderPermission.CHILDREN, can_edit=FolderPermission.ALLOW, can_read=FolderPermission.ALLOW, can_add_children=FolderPermission.ALLOW)
            fp1.groups.add(self.group1)
            fp2.groups.add(self.group3)

            self.assertEqual(FolderPermission.objects.count(), 2)

            # We have to invalidate cache
            delattr(self.folder, 'permission_cache')

            self.assertEqual(self.test_user1.groups.filter(pk=self.group1.pk).exists(), True)
            self.assertEqual(self.test_user1.groups.filter(pk=self.group3.pk).exists(), False)

            self.assertEqual(self.folder.has_read_permission(request1), True)
            self.assertEqual(self.folder.has_edit_permission(request1), False)

            self.assertEqual(self.test_user1.groups.count(), 2)

            self.test_user1.groups.add(self.group3)

            self.assertEqual(self.test_user1.groups.count(), 3)

            # We have to invalidate cache
            delattr(self.folder, 'permission_cache')

            self.assertEqual(self.folder.has_read_permission(request1), True)
            self.assertEqual(self.folder.has_edit_permission(request1), False)

        finally:
            filer_settings.FILER_ENABLE_PERMISSIONS = old_setting

    def test_overlapped_groups_deny2(self):
        # Tests overlapped groups with explicit deny
        # Similar test to test_overlapped_groups_deny1, only order of groups is different

        request2 = Mock()
        setattr(request2, 'user', self.test_user2)

        old_setting = filer_settings.FILER_ENABLE_PERMISSIONS
        try:
            filer_settings.FILER_ENABLE_PERMISSIONS = True

            self.assertEqual(self.folder.has_read_permission(request2), False)
            self.assertEqual(self.folder_perm.has_read_permission(request2), False)

            self.assertEqual(FolderPermission.objects.count(), 0)

            fp1 = FolderPermission.objects.create(folder=self.folder_perm, type=FolderPermission.CHILDREN, can_edit=FolderPermission.DENY, can_read=FolderPermission.ALLOW, can_add_children=FolderPermission.DENY)
            fp2 = FolderPermission.objects.create(folder=self.folder_perm, type=FolderPermission.CHILDREN, can_edit=FolderPermission.ALLOW, can_read=FolderPermission.ALLOW, can_add_children=FolderPermission.ALLOW)
            fp1.groups.add(self.group4)
            fp2.groups.add(self.group1)
            self.assertEqual(FolderPermission.objects.count(), 2)

            # We have to invalidate cache
            delattr(self.folder_perm, 'permission_cache')

            self.assertEqual(self.test_user2.groups.filter(pk=self.group4.pk).exists(), True)
            self.assertEqual(self.test_user2.groups.filter(pk=self.group1.pk).exists(), False)

            self.assertEqual(self.folder_perm.has_read_permission(request2), True)
            self.assertEqual(self.folder_perm.has_edit_permission(request2), False)

            self.assertEqual(self.test_user2.groups.count(), 2)

            self.test_user2.groups.add(self.group1)

            self.assertEqual(self.test_user2.groups.count(), 3)

            # We have to invalidate cache
            delattr(self.folder_perm, 'permission_cache')

            self.assertEqual(self.folder_perm.has_read_permission(request2), True)
            self.assertEqual(self.folder_perm.has_edit_permission(request2), False)

        finally:
            filer_settings.FILER_ENABLE_PERMISSIONS = old_setting

    def test_overlapped_groups1(self):
        # Tests overlapped groups without explicit deny

        request1 = Mock()
        setattr(request1, 'user', self.test_user1)

        old_setting = filer_settings.FILER_ENABLE_PERMISSIONS
        try:
            filer_settings.FILER_ENABLE_PERMISSIONS = True

            self.assertEqual(self.folder.has_read_permission(request1), False)
            self.assertEqual(self.folder_perm.has_read_permission(request1), False)

            self.assertEqual(FolderPermission.objects.count(), 0)

            fp1 = FolderPermission.objects.create(folder=self.folder, type=FolderPermission.CHILDREN, can_edit=None, can_read=FolderPermission.ALLOW, can_add_children=None)
            fp2 = FolderPermission.objects.create(folder=self.folder, type=FolderPermission.CHILDREN, can_edit=FolderPermission.ALLOW, can_read=FolderPermission.ALLOW, can_add_children=FolderPermission.ALLOW)
            fp1.groups.add(self.group1)
            fp2.groups.add(self.group3)
            self.assertEqual(FolderPermission.objects.count(), 2)

            # We have to invalidate cache
            delattr(self.folder, 'permission_cache')

            self.assertEqual(self.test_user1.groups.filter(pk=self.group1.pk).exists(), True)
            self.assertEqual(self.test_user1.groups.filter(pk=self.group3.pk).exists(), False)

            self.assertEqual(self.folder.has_read_permission(request1), True)
            self.assertEqual(self.folder.has_edit_permission(request1), False)

            self.assertEqual(self.test_user1.groups.count(), 2)

            self.test_user1.groups.add(self.group3)

            self.assertEqual(self.test_user1.groups.count(), 3)

            # We have to invalidate cache
            delattr(self.folder, 'permission_cache')

            self.assertEqual(self.folder.has_read_permission(request1), True)
            self.assertEqual(self.folder.has_edit_permission(request1), True)

        finally:
            filer_settings.FILER_ENABLE_PERMISSIONS = old_setting

    def test_overlapped_groups2(self):
        # Tests overlapped groups without explicit deny
        # Similar test to test_overlapped_groups1, only order of groups is different

        request2 = Mock()
        setattr(request2, 'user', self.test_user2)

        old_setting = filer_settings.FILER_ENABLE_PERMISSIONS
        try:
            filer_settings.FILER_ENABLE_PERMISSIONS = True

            self.assertEqual(self.folder.has_read_permission(request2), False)
            self.assertEqual(self.folder_perm.has_read_permission(request2), False)

            self.assertEqual(FolderPermission.objects.count(), 0)

            fp1 = FolderPermission.objects.create(folder=self.folder_perm, type=FolderPermission.CHILDREN, can_edit=None, can_read=FolderPermission.ALLOW, can_add_children=None)
            fp2 = FolderPermission.objects.create(folder=self.folder_perm, type=FolderPermission.CHILDREN, can_edit=FolderPermission.ALLOW, can_read=FolderPermission.ALLOW, can_add_children=FolderPermission.ALLOW)
            fp1.groups.add(self.group3)
            fp2.groups.add(self.group1)
            self.assertEqual(FolderPermission.objects.count(), 2)

            # We have to invalidate cache
            delattr(self.folder_perm, 'permission_cache')

            self.assertEqual(self.test_user2.groups.filter(pk=self.group3.pk).exists(), True)
            self.assertEqual(self.test_user2.groups.filter(pk=self.group1.pk).exists(), False)

            self.assertEqual(self.folder_perm.has_read_permission(request2), True)
            self.assertEqual(self.folder_perm.has_edit_permission(request2), False)

            self.assertEqual(self.test_user2.groups.count(), 2)

            self.test_user2.groups.add(self.group1)

            self.assertEqual(self.test_user2.groups.count(), 3)

            # We have to invalidate cache
            delattr(self.folder_perm, 'permission_cache')

            self.assertEqual(self.folder_perm.has_read_permission(request2), True)
            self.assertEqual(self.folder_perm.has_edit_permission(request2), True)

        finally:
            filer_settings.FILER_ENABLE_PERMISSIONS = old_setting

    def test_multi_user_permission(self):
        # Tests folders with multiple users associated to it
        # A user not associated won't be able to access it

        request3 = Mock()
        setattr(request3, 'user', self.test_user3)

        old_setting = filer_settings.FILER_ENABLE_PERMISSIONS
        try:
            filer_settings.FILER_ENABLE_PERMISSIONS = True

            self.assertEqual(self.folder.has_read_permission(request3), False)
            self.assertEqual(self.folder_perm.has_read_permission(request3), False)

            self.assertEqual(FolderPermission.objects.count(), 0)

            fp1 = FolderPermission.objects.create(folder=self.folder_perm, type=FolderPermission.CHILDREN, can_edit=FolderPermission.ALLOW, can_read=FolderPermission.ALLOW, can_add_children=None)
            fp2 = FolderPermission.objects.create(folder=self.folder, type=FolderPermission.CHILDREN, can_edit=FolderPermission.ALLOW, can_read=FolderPermission.ALLOW, can_add_children=None)
            fp1.users.add(self.test_user1, self.test_user2)
            fp2.users.add(self.test_user3)
            self.assertEqual(FolderPermission.objects.count(), 2)

            # We have to invalidate cache
            delattr(self.folder_perm, 'permission_cache')
            delattr(self.folder, 'permission_cache')

            self.assertEqual(self.folder_perm.has_read_permission(request3), False)
            self.assertEqual(self.folder_perm.has_edit_permission(request3), False)
            self.assertEqual(self.folder.has_read_permission(request3), True)
            self.assertEqual(self.folder.has_edit_permission(request3), True)

            fp1.users.add(self.test_user3)

            # We have to invalidate cache
            delattr(self.folder_perm, 'permission_cache')
            delattr(self.folder, 'permission_cache')

            self.assertEqual(self.folder_perm.has_read_permission(request3), True)
            self.assertEqual(self.folder_perm.has_edit_permission(request3), True)
            self.assertEqual(self.folder.has_read_permission(request3), True)
            self.assertEqual(self.folder.has_edit_permission(request3), True)

        finally:
            filer_settings.FILER_ENABLE_PERMISSIONS = old_setting
