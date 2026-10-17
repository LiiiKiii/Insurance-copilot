"""Focused role-helper tests using real model instances without database I/O."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from fastapi import HTTPException

from admin.dependencies import has_admin_access, is_admin_role, require_role, require_superadmin


class AuthenticationDependencyTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _user(*roles: tuple[str, str], superadmin: bool = False, tenant_id: str = "tenant-a"):
        return SimpleNamespace(
            tenant_id=tenant_id,
            is_superadmin=superadmin,
            roles=[SimpleNamespace(name=name, tenant_id=role_tenant) for name, role_tenant in roles],
        )

    async def test_role_helpers_honor_exact_role_names_and_tenant_scope(self) -> None:
        admin = self._user(("admin", "tenant-a"))
        manager = self._user(("agent_manager", "tenant-a"))
        readonly = self._user(("readonly", "tenant-a"))
        unrelated = self._user(("admin", "tenant-b"))

        self.assertTrue(is_admin_role(admin))
        self.assertTrue(has_admin_access(admin))
        self.assertFalse(is_admin_role(manager))
        self.assertTrue(has_admin_access(manager))
        self.assertTrue(has_admin_access(readonly))
        self.assertFalse(has_admin_access(unrelated))
        self.assertTrue(is_admin_role(self._user(superadmin=True)))

    async def test_role_guards_allow_only_expected_roles(self) -> None:
        admin_guard = require_role("super_admin", "admin")
        manager_guard = require_role("super_admin", "admin", "agent_manager")
        admin = self._user(("admin", "tenant-a"))
        manager = self._user(("agent_manager", "tenant-a"))
        readonly = self._user(("readonly", "tenant-a"))

        self.assertIs(await admin_guard(admin), admin)
        self.assertIs(await manager_guard(manager), manager)
        with self.assertRaises(HTTPException) as denied:
            await admin_guard(readonly)
        self.assertEqual(denied.exception.status_code, 403)
        with self.assertRaises(HTTPException):
            await require_superadmin(admin)
        root = self._user(superadmin=True)
        self.assertIs(await require_superadmin(root), root)


if __name__ == "__main__":
    unittest.main()
