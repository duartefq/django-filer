# -*- coding: utf-8 -*-
from __future__ import absolute_import

from django.contrib import admin
from django.contrib.admin.filters import RelatedOnlyFieldListFilter

from .. import settings
from ..fields import folder


class PermissionAdmin(admin.ModelAdmin):
    fieldsets = (
        (None, {'fields': (('type', 'folder', ))}),
        (None, {'fields': ('users',)}),
        (None, {'fields': ('groups',)}),
        (None, {'fields': (
            ('can_edit', 'can_read', 'can_add_children')
        )}),
    )
    raw_id_fields = ('user',)
    list_filter = [('users', RelatedOnlyFieldListFilter),
                   ('groups', RelatedOnlyFieldListFilter),
                   'can_edit', 'can_read']
    list_display = ['__str__', 'folder']
    search_fields = ('folder__name',)
    filter_horizontal = ('groups', 'users')

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        db = kwargs.get('using')
        if db_field.name == 'folder':
            kwargs['widget'] = folder.AdminFolderWidget(
                db_field.rel, self.admin_site, using=db)
        return super(PermissionAdmin, self).formfield_for_foreignkey(
            db_field, request, **kwargs)

    def get_model_perms(self, request):
        # don't display the permissions admin if permissions are disabled.
        # This method is easier for testing than not registering the admin
        # at all at import time
        enable_permissions = settings.FILER_ENABLE_PERMISSIONS and \
            request.user.has_perm('filer.add_folderpermission')
        return {
            'add': enable_permissions,
            'change': enable_permissions,
            'delete': enable_permissions,
        }
