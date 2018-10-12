"""
Tests for the Certificate REST APIs.
"""
# pylint: disable=missing-docstring
from itertools import product
import ddt

from django.urls import reverse
from django.utils import timezone
from freezegun import freeze_time
from rest_framework import status
from rest_framework.test import APITestCase

from course_modes.models import CourseMode
from lms.djangoapps.certificates.apis.v0.views import CertificatesDetailView
from lms.djangoapps.certificates.models import CertificateStatuses
from lms.djangoapps.certificates.tests.factories import GeneratedCertificateFactory
from openedx.core.djangoapps.oauth_dispatch.toggles import ENFORCE_JWT_SCOPES
from openedx.core.djangoapps.user_authn.tests.utils import AuthType, AuthAndScopesTestMixin
from student.tests.factories import UserFactory
from xmodule.modulestore.tests.django_utils import SharedModuleStoreTestCase
from xmodule.modulestore.tests.factories import CourseFactory


@ddt.ddt
class CertificatesRestApiTest(AuthAndScopesTestMixin, SharedModuleStoreTestCase, APITestCase):
    """
    Test for the Certificates REST APIs
    """
    shard = 4
    now = timezone.now()
    default_required_scopes = CertificatesDetailView.required_scopes

    @classmethod
    def setUpClass(cls):
        super(CertificatesRestApiTest, cls).setUpClass()
        cls.course = CourseFactory.create(
            org='edx',
            number='verified',
            display_name='Verified Course'
        )

    def setUp(self):
        freezer = freeze_time(self.now)
        freezer.start()
        self.addCleanup(freezer.stop)

        super(CertificatesRestApiTest, self).setUp()

        self.staff_user = UserFactory.create(password=self.user_password, is_staff=True)
        self.student_no_cert = UserFactory.create(password=self.user_password)

        GeneratedCertificateFactory.create(
            user=self.student,
            course_id=self.course.id,
            status=CertificateStatuses.downloadable,
            mode='verified',
            download_url='www.google.com',
            grade="0.88"
        )

        self.namespaced_url = 'certificates_api:v0:certificates:detail'

    def _assert_certificate_response(self, response):
        self.assertEqual(
            response.data,
            {
                'username': self.student.username,
                'status': CertificateStatuses.downloadable,
                'is_passing': True,
                'grade': '0.88',
                'download_url': 'www.google.com',
                'certificate_type': CourseMode.VERIFIED,
                'course_id': unicode(self.course.id),
                'created_date': self.now,
            }
        )

    def get_url(self, username):
        """
        Helper function to create the url for certificates
        """
        return reverse(
            self.namespaced_url,
            kwargs={
                'course_id': self.course.id,
                'username': username
            }
        )

    def test_anonymous_user(self):
        resp = self.client.get(self.get_url(self.student.username))
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    @ddt.data(*list(AuthType))
    def test_no_certificate(self, auth_type):
        resp = self._get_response(
            auth_type,
            requesting_user=self.student_no_cert,
            requested_user=self.student_no_cert,
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn('error_code', resp.data)
        self.assertEqual(
            resp.data['error_code'],
            'no_certificate_for_user',
        )

    @ddt.data(*product(list(AuthType), (True, False)))
    @ddt.unpack
    def test_self_user(self, auth_type, scopes_enforced):
        with ENFORCE_JWT_SCOPES.override(active=scopes_enforced):
            resp = self._get_response(auth_type)
            self.assertEqual(resp.status_code, status.HTTP_200_OK)
            self._assert_certificate_response(resp)

    @ddt.data(*product(list(AuthType), (True, False)))
    @ddt.unpack
    def test_inactive_user(self, auth_type, scopes_enforced):
        with ENFORCE_JWT_SCOPES.override(active=scopes_enforced):
            self.student.is_active = False
            self.student.save()

            resp = self._get_response(auth_type)
            self.assertEqual(resp.status_code, status.HTTP_200_OK)

    @ddt.data(*product(list(AuthType), (True, False)))
    @ddt.unpack
    def test_staff_user(self, auth_type, scopes_enforced):
        with ENFORCE_JWT_SCOPES.override(active=scopes_enforced):
            resp = self._get_response(auth_type, requesting_user=self.staff_user)
            self.assertEqual(resp.status_code, status.HTTP_200_OK)
