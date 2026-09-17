"""Kiểm thử luồng HTTP thật: authentication, forms, CSRF và phân quyền."""

from urllib.parse import parse_qs

from django.contrib.admin.models import LogEntry
from django.contrib.auth import SESSION_KEY, get_user_model
from django.test import Client
from django.urls import reverse

from apps.accounts.services import set_account_active

from . import AccountTestCase, NEW_PASSWORD, TEST_PASSWORD


class AuthenticationViewTests(AccountTestCase):
    def test_login_page_renders_and_valid_credentials_start_session(self):
        self.assertEqual(self.client.get(reverse("accounts:login")).status_code, 200)
        response = self.client.post(
            reverse("accounts:login"),
            {"username": self.employee.username, "password": TEST_PASSWORD},
        )
        self.assertRedirects(response, reverse("accounts:workspace"))
        self.assertEqual(self.client.session[SESSION_KEY], str(self.employee.pk))

    def test_wrong_password_or_locked_user_cannot_log_in(self):
        for username, password in (
            (self.employee.username, "incorrect-test-password"),
            (self.inactive_employee.username, TEST_PASSWORD),
            ("nonexistent_username", TEST_PASSWORD),
        ):
            with self.subTest(username=username):
                response = self.client.post(
                    reverse("accounts:login"),
                    {"username": username, "password": password},
                )
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].errors)
                self.assertNotIn(SESSION_KEY, self.client.session)

    def test_login_rejects_external_next_url(self):
        for next_url in ("https://untrusted.example/path", "//untrusted.example/"):
            with self.subTest(next_url=next_url):
                self.client.logout()
                response = self.client.post(
                    reverse("accounts:login"),
                    {
                        "username": self.employee.username,
                        "password": TEST_PASSWORD,
                        "next": next_url,
                    },
                )
                self.assertRedirects(response, reverse("accounts:workspace"))

    def test_login_accepts_same_site_next_url(self):
        response = self.client.post(
            reverse("accounts:login"),
            {
                "username": self.manager.username,
                "password": TEST_PASSWORD,
                "next": reverse("accounts:account_list"),
            },
        )
        self.assertRedirects(response, reverse("accounts:account_list"))

    def test_logout_requires_post_and_clears_session(self):
        self.client.force_login(self.employee)
        self.assertEqual(
            self.client.get(reverse("accounts:logout")).status_code, 405
        )
        self.assertIn(SESSION_KEY, self.client.session)
        response = self.client.post(reverse("accounts:logout"))
        self.assertEqual(response.status_code, 302)
        self.assertNotIn(SESSION_KEY, self.client.session)
        self.assertEqual(
            self.client.get(reverse("accounts:workspace")).status_code, 302
        )

    def test_workspace_and_password_change_require_authentication(self):
        for name in ("workspace", "password_change", "password_change_done"):
            with self.subTest(name=name):
                response = self.client.get(reverse(f"accounts:{name}"))
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response.url.startswith(reverse("accounts:login")))

    def test_password_change_checks_old_password_confirmation_and_strength(self):
        self.client.force_login(self.employee)
        invalid_passwords = (
            ("wrong-old-password", NEW_PASSWORD, NEW_PASSWORD),
            (TEST_PASSWORD, NEW_PASSWORD, "Different-Password!3865"),
            (TEST_PASSWORD, "123", "123"),
            (TEST_PASSWORD, "1234567890", "1234567890"),
        )
        for old_password, new_password1, new_password2 in invalid_passwords:
            with self.subTest(old_password=old_password, new_password=new_password1):
                response = self.client.post(
                    reverse("accounts:password_change"),
                    {
                        "old_password": old_password,
                        "new_password1": new_password1,
                        "new_password2": new_password2,
                    },
                )
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].errors)
                self.employee.refresh_from_db()
                self.assertTrue(self.employee.check_password(TEST_PASSWORD))

    def test_successful_password_change_preserves_current_session(self):
        self.client.force_login(self.employee)
        response = self.client.post(
            reverse("accounts:password_change"),
            {
                "old_password": TEST_PASSWORD,
                "new_password1": NEW_PASSWORD,
                "new_password2": NEW_PASSWORD,
            },
        )
        self.assertRedirects(response, reverse("accounts:password_change_done"))
        self.employee.refresh_from_db()
        self.assertTrue(self.employee.check_password(NEW_PASSWORD))
        self.assertFalse(self.employee.check_password(TEST_PASSWORD))
        self.assertEqual(self.client.session[SESSION_KEY], str(self.employee.pk))
        self.assertEqual(
            self.client.get(reverse("accounts:workspace")).status_code, 200
        )

    def test_authentication_posts_are_protected_by_csrf(self):
        csrf_client = Client(enforce_csrf_checks=True)
        response = csrf_client.post(
            reverse("accounts:login"),
            {"username": self.employee.username, "password": TEST_PASSWORD},
        )
        self.assertEqual(response.status_code, 403)
        csrf_client.force_login(self.employee)
        for name in ("password_change", "logout"):
            with self.subTest(name=name):
                self.assertEqual(
                    csrf_client.post(reverse(f"accounts:{name}")).status_code, 403
                )


class AccountManagementViewTests(AccountTestCase):
    def setUp(self):
        self.client.force_login(self.manager)

    def test_manager_can_view_account_list(self):
        response = self.client.get(reverse("accounts:account_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.employee.username)
        self.assertIn("filter_form", response.context)
        self.assertIn("page_obj", response.context)

    def test_anonymous_user_is_redirected_and_employee_is_forbidden(self):
        urls = [reverse("accounts:account_list")]
        urls.extend(
            reverse(f"accounts:{name}", kwargs={"pk": self.employee.pk})
            for name in ("account_lock", "account_unlock", "password_reset")
        )
        self.client.logout()
        for url in urls:
            with self.subTest(url=url, actor="anonymous"):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response.url.startswith(reverse("accounts:login")))
        self.client.force_login(self.employee)
        for url in urls:
            with self.subTest(url=url, actor="employee"):
                self.assertEqual(self.client.get(url).status_code, 403)
                self.assertEqual(self.client.post(url).status_code, 403)
        self.employee.refresh_from_db()
        self.assertTrue(self.employee.is_active)
        self.assertTrue(self.employee.check_password(TEST_PASSWORD))

    def test_staff_flag_does_not_grant_employee_account_or_admin_access(self):
        self.employee.is_staff = True
        self.employee.save()
        self.client.force_login(self.employee)
        self.assertEqual(
            self.client.get(reverse("accounts:account_list")).status_code, 403
        )
        response = self.client.get(reverse("admin:index"))
        self.assertIn(response.status_code, (302, 403))
        workspace = self.client.get(reverse("accounts:workspace"))
        self.assertNotContains(
            workspace, f'href="{reverse("accounts:account_list")}"'
        )
        self.assertNotContains(workspace, f'href="{reverse("admin:index")}"')

    def test_manager_navigation_has_account_management_link(self):
        response = self.client.get(reverse("accounts:workspace"))
        self.assertContains(
            response, f'href="{reverse("accounts:account_list")}"'
        )

    def test_search_matches_username_and_email_case_insensitively(self):
        for query in ("EMPLOYEE_TEST", "EMPLOYEE@EXAMPLE.TEST"):
            with self.subTest(query=query):
                response = self.client.get(
                    reverse("accounts:account_list"), {"q": query, "status": "active"}
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    [user.pk for user in response.context["page_obj"]],
                    [self.employee.pk],
                )

    def test_status_filter_shows_only_matching_accounts(self):
        response = self.client.get(
            reverse("accounts:account_list"), {"status": "inactive"}
        )
        self.assertEqual(
            [user.pk for user in response.context["page_obj"]],
            [self.inactive_employee.pk],
        )
        response = self.client.get(
            reverse("accounts:account_list"), {"status": "active"}
        )
        self.assertTrue(all(user.is_active for user in response.context["page_obj"]))
        self.assertNotIn(
            self.inactive_employee.pk,
            [user.pk for user in response.context["page_obj"]],
        )

    def test_invalid_status_is_validated_instead_of_silently_showing_all(self):
        response = self.client.get(
            reverse("accounts:account_list"), {"status": "not-a-status"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["filter_form"].errors)

    def test_pagination_has_twenty_rows_and_preserves_search_and_status(self):
        get_user_model().objects.bulk_create(
            [
                get_user_model()(username=f"pagination_case_{number:02}")
                for number in range(23)
            ]
        )
        filters = {"q": "pagination_case", "status": "active"}
        first = self.client.get(reverse("accounts:account_list"), filters)
        self.assertEqual(len(first.context["page_obj"]), 20)
        second = self.client.get(
            reverse("accounts:account_list"), {**filters, "page": 2}
        )
        self.assertEqual(len(second.context["page_obj"]), 3)
        self.assertEqual(second.context["page_obj"].paginator.count, 23)
        params = parse_qs(second.context["query_string"])
        self.assertEqual(params.get("q"), [filters["q"]])
        self.assertEqual(params.get("status"), ["active"])
        self.assertNotIn("page", params)
        self.assertFalse(
            {user.pk for user in first.context["page_obj"]}
            & {user.pk for user in second.context["page_obj"]}
        )

    def test_no_search_results_renders_empty_list(self):
        response = self.client.get(
            reverse("accounts:account_list"), {"q": "no_matching_username_98231"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].paginator.count, 0)

    def test_lock_get_only_confirms_and_post_locks_without_deleting(self):
        url = reverse("accounts:account_lock", kwargs={"pk": self.employee.pk})
        original_count = get_user_model().objects.count()
        self.assertEqual(self.client.get(url).status_code, 200)
        self.employee.refresh_from_db()
        self.assertTrue(self.employee.is_active)
        response = self.client.post(url)
        self.assertRedirects(response, reverse("accounts:account_list"))
        self.employee.refresh_from_db()
        self.assertFalse(self.employee.is_active)
        self.assertEqual(get_user_model().objects.count(), original_count)

    def test_unlock_get_only_confirms_and_post_unlocks(self):
        url = reverse(
            "accounts:account_unlock", kwargs={"pk": self.inactive_employee.pk}
        )
        self.assertEqual(self.client.get(url).status_code, 200)
        self.inactive_employee.refresh_from_db()
        self.assertFalse(self.inactive_employee.is_active)
        response = self.client.post(url)
        self.assertRedirects(response, reverse("accounts:account_list"))
        self.inactive_employee.refresh_from_db()
        self.assertTrue(self.inactive_employee.is_active)

    def test_manager_cannot_mutate_another_manager_or_self_over_http(self):
        for target in (self.manager, self.other_manager):
            for name in ("account_lock", "account_unlock", "password_reset"):
                with self.subTest(target=target.username, name=name):
                    url = reverse(f"accounts:{name}", kwargs={"pk": target.pk})
                    self.assertEqual(self.client.get(url).status_code, 403)
                    response = self.client.post(
                        url,
                        {
                            "new_password1": NEW_PASSWORD,
                            "new_password2": NEW_PASSWORD,
                        },
                    )
                    self.assertEqual(response.status_code, 403)
                    target.refresh_from_db()
                    self.assertTrue(target.is_active)
                    self.assertTrue(target.check_password(TEST_PASSWORD))

    def test_missing_target_returns_404(self):
        for name in ("account_lock", "account_unlock", "password_reset"):
            with self.subTest(name=name):
                url = reverse(f"accounts:{name}", kwargs={"pk": 99999999})
                self.assertEqual(self.client.get(url).status_code, 404)
                self.assertEqual(self.client.post(url).status_code, 404)

    def test_manager_reset_password_validates_confirmation_and_strength(self):
        url = reverse("accounts:password_reset", kwargs={"pk": self.employee.pk})
        self.assertEqual(self.client.get(url).status_code, 200)
        for password1, password2 in (
            (NEW_PASSWORD, "Mismatched!3982"),
            ("123", "123"),
            ("1234567890", "1234567890"),
        ):
            with self.subTest(password1=password1):
                response = self.client.post(
                    url,
                    {"new_password1": password1, "new_password2": password2},
                )
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].errors)
                self.employee.refresh_from_db()
                self.assertTrue(self.employee.check_password(TEST_PASSWORD))

    def test_manager_can_reset_employee_password(self):
        response = self.client.post(
            reverse("accounts:password_reset", kwargs={"pk": self.employee.pk}),
            {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD},
        )
        self.assertRedirects(response, reverse("accounts:account_list"))
        self.employee.refresh_from_db()
        self.assertTrue(self.employee.check_password(NEW_PASSWORD))
        self.assertFalse(self.employee.check_password(TEST_PASSWORD))

    def test_account_mutations_require_csrf_token(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.manager)
        for name in ("account_lock", "account_unlock", "password_reset"):
            with self.subTest(name=name):
                url = reverse(f"accounts:{name}", kwargs={"pk": self.employee.pk})
                self.assertEqual(csrf_client.post(url).status_code, 403)
        self.employee.refresh_from_db()
        self.assertTrue(self.employee.is_active)
        self.assertTrue(self.employee.check_password(TEST_PASSWORD))
        lock_url = reverse("accounts:account_lock", kwargs={"pk": self.employee.pk})
        self.assertEqual(csrf_client.get(lock_url).status_code, 200)
        response = csrf_client.post(
            lock_url, HTTP_X_CSRFTOKEN=csrf_client.cookies["csrftoken"].value
        )
        self.assertEqual(response.status_code, 302)
        self.employee.refresh_from_db()
        self.assertFalse(self.employee.is_active)

    def test_put_cannot_mutate_account_status_or_passwords(self):
        urls = [reverse("accounts:password_change")]
        urls.extend(
            reverse(f"accounts:{name}", kwargs={"pk": self.employee.pk})
            for name in ("account_lock", "account_unlock", "password_reset")
        )
        for url in urls:
            with self.subTest(url=url):
                response = self.client.put(
                    url,
                    {
                        "is_active": False,
                        "old_password": TEST_PASSWORD,
                        "new_password1": NEW_PASSWORD,
                        "new_password2": NEW_PASSWORD,
                    },
                    content_type="application/json",
                )
                self.assertEqual(response.status_code, 405)
        for user in (self.employee, self.manager):
            user.refresh_from_db()
            self.assertTrue(user.is_active)
            self.assertTrue(user.check_password(TEST_PASSWORD))

    def test_manager_can_create_view_and_update_employee_account(self):
        create_response = self.client.post(
            reverse("accounts:account_create"),
            {
                "username": "new_waiter",
                "email": "NEW_WAITER@EXAMPLE.TEST",
                "first_name": "New",
                "last_name": "Waiter",
                "password1": NEW_PASSWORD,
                "password2": NEW_PASSWORD,
            },
        )
        self.assertRedirects(create_response, reverse("accounts:account_list"))
        account = get_user_model().objects.get(username="new_waiter")
        self.assertEqual(account.email, "new_waiter@example.test")
        self.assertEqual(
            self.client.get(reverse("accounts:account_detail", kwargs={"pk": account.pk})).status_code,
            200,
        )
        update_response = self.client.post(
            reverse("accounts:account_update", kwargs={"pk": account.pk}),
            {
                "username": "updated_waiter",
                "email": "updated@example.test",
                "first_name": "Updated",
                "last_name": "Waiter",
                "is_active": "on",
            },
        )
        self.assertRedirects(update_response, reverse("accounts:account_list"))
        account.refresh_from_db()
        self.assertEqual(account.username, "updated_waiter")
        self.assertEqual(account.get_full_name(), "Updated Waiter")

    def test_employee_cannot_use_account_crud_endpoints(self):
        self.client.force_login(self.employee)
        for url in (
            reverse("accounts:account_create"),
            reverse("accounts:account_detail", kwargs={"pk": self.inactive_employee.pk}),
            reverse("accounts:account_update", kwargs={"pk": self.inactive_employee.pk}),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)


class UserAdminViewTests(AccountTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.superuser = get_user_model().objects.create_superuser(
            username="superadmin_test", password=TEST_PASSWORD
        )

    def test_superuser_can_create_employee_and_manager_through_admin(self):
        self.client.force_login(self.superuser)
        url = reverse("admin:accounts_user_add")
        self.assertEqual(self.client.get(url).status_code, 200)
        for role in ("EMPLOYEE", "MANAGER"):
            with self.subTest(role=role):
                username = f"created_{role.lower()}"
                response = self.client.post(
                    url,
                    {
                        "username": username,
                        "email": f"{username}@example.test",
                        "role": role,
                        "is_active": "on",
                        "password1": NEW_PASSWORD,
                        "password2": NEW_PASSWORD,
                        "_save": "1",
                    },
                )
                self.assertEqual(response.status_code, 302)
                created_user = get_user_model().objects.get(username=username)
                self.assertEqual(created_user.role, role)
                self.assertTrue(created_user.is_active)
                self.assertFalse(created_user.is_superuser)
                self.assertFalse(created_user.is_staff)
                self.assertTrue(created_user.check_password(NEW_PASSWORD))
                self.assertTrue(
                    Client().login(username=username, password=NEW_PASSWORD)
                )

    def test_admin_user_creation_rejects_invalid_role_and_password(self):
        self.client.force_login(self.superuser)
        for role, password in (("CASHIER", NEW_PASSWORD), ("EMPLOYEE", "123")):
            with self.subTest(role=role, password=password):
                response = self.client.post(
                    reverse("admin:accounts_user_add"),
                    {
                        "username": "invalid_new_account",
                        "role": role,
                        "is_active": "on",
                        "password1": password,
                        "password2": password,
                        "_save": "1",
                    },
                )
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["adminform"].form.errors)
                self.assertFalse(
                    get_user_model().objects.filter(
                        username="invalid_new_account"
                    ).exists()
                )

    def test_employee_with_staff_flag_cannot_log_in_at_admin_login(self):
        self.employee.is_staff = True
        self.employee.save()
        response = self.client.post(
            reverse("admin:login"),
            {
                "username": self.employee.username,
                "password": TEST_PASSWORD,
                "next": reverse("admin:index"),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_admin_lock_and_unlock_also_revoke_existing_session(self):
        employee_client = Client()
        employee_client.force_login(self.employee)
        self.client.force_login(self.superuser)
        url = reverse("admin:accounts_user_change", args=[self.employee.pk])
        form_data = {
            "username": self.employee.username,
            "email": self.employee.email,
            "role": "EMPLOYEE",
            "_save": "1",
        }
        response = self.client.post(url, form_data)
        self.assertEqual(response.status_code, 302)
        self.employee.refresh_from_db()
        self.assertFalse(self.employee.is_active)
        response = self.client.post(url, {**form_data, "is_active": "on"})
        self.assertEqual(response.status_code, 302)
        self.employee.refresh_from_db()
        self.assertTrue(self.employee.is_active)
        self.assertEqual(
            employee_client.get(reverse("accounts:workspace")).status_code, 302
        )
        self.assertTrue(self.employee.check_password(TEST_PASSWORD))

    def test_superuser_cannot_delete_accounts_in_admin(self):
        self.client.force_login(self.superuser)
        url = reverse("admin:accounts_user_delete", args=[self.employee.pk])
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url, {"post": "yes"}).status_code, 403)
        self.assertTrue(get_user_model().objects.filter(pk=self.employee.pk).exists())

    def test_staff_manager_cannot_escalate_account_privileges_through_admin(self):
        self.manager.is_staff = True
        self.manager.save()
        self.client.force_login(self.manager)
        url = reverse("admin:accounts_user_change", args=[self.employee.pk])
        self.assertEqual(self.client.get(url).status_code, 403)
        response = self.client.post(
            url,
            {
                "username": self.employee.username,
                "role": "MANAGER",
                "is_staff": "on",
                "is_superuser": "on",
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 403)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.role, "EMPLOYEE")
        self.assertFalse(self.employee.is_superuser)

    def test_audit_entries_are_viewable_but_cannot_be_added_changed_or_deleted(self):
        set_account_active(
            actor=self.manager, target_id=self.employee.pk, is_active=False
        )
        entry = LogEntry.objects.get()
        original_message = entry.change_message
        self.client.force_login(self.superuser)
        self.assertEqual(
            self.client.get(reverse("admin:admin_logentry_changelist")).status_code,
            200,
        )
        change_url = reverse("admin:admin_logentry_change", args=[entry.pk])
        self.assertEqual(self.client.get(change_url).status_code, 200)
        self.assertEqual(
            self.client.post(change_url, {"change_message": "tampered"}).status_code,
            403,
        )
        for url in (
            reverse("admin:admin_logentry_add"),
            reverse("admin:admin_logentry_delete", args=[entry.pk]),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)
                self.assertEqual(self.client.post(url, {"post": "yes"}).status_code, 403)
        entry.refresh_from_db()
        self.assertEqual(entry.change_message, original_message)
        self.assertEqual(LogEntry.objects.count(), 1)
