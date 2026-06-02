import threading
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import IntegrityError, connection
from django.test import Client, TestCase, TransactionTestCase

from .models import Patient, Compte, Utilisateur, ensure_patient_for_user


class ClosedExtranetAuthTests(TestCase):
    def test_signup_get_redirects_to_login(self):
        response = Client().get('/signup/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/login/')

    def test_signup_post_does_not_create_user(self):
        before = User.objects.count()
        response = Client().post('/signup/', {
            'first_name': 'Nouveau',
            'last_name': 'Patient',
            'email': 'nouveau.patient@test.com',
            'password1': 'Secret123!',
            'password2': 'Secret123!',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/login/')
        self.assertEqual(User.objects.count(), before)
        self.assertFalse(User.objects.filter(email='nouveau.patient@test.com').exists())

    def test_login_page_accessible(self):
        response = Client().get('/login/')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Créer un compte')
        self.assertNotContains(response, '/signup/')


class PatientUniqueIdTests(TransactionTestCase):
    reset_sequences = True

    def _create_user(self, email):
        return User.objects.create_user(
            username=email,
            email=email,
            password='testpass123',
        )

    def test_patient_id_auto_increment_unique(self):
        u1 = self._create_user('p1@test.com')
        u2 = self._create_user('p2@test.com')
        p1 = ensure_patient_for_user(u1, nom='Patient Un')
        p2 = ensure_patient_for_user(u2, nom='Patient Deux')
        self.assertNotEqual(p1.id, p2.id)
        self.assertTrue(p1.id > 0 and p2.id > 0)

    def test_patient_reference_uuid_unique(self):
        u1 = self._create_user('ref1@test.com')
        u2 = self._create_user('ref2@test.com')
        p1 = ensure_patient_for_user(u1)
        p2 = ensure_patient_for_user(u2)
        self.assertIsNotNone(p1.reference)
        self.assertIsNotNone(p2.reference)
        self.assertNotEqual(p1.reference, p2.reference)

    def test_one_patient_per_user(self):
        user = self._create_user('solo@test.com')
        p1 = ensure_patient_for_user(user, nom='A')
        p2 = ensure_patient_for_user(user, nom='B')
        self.assertEqual(p1.id, p2.id)
        self.assertEqual(Patient.objects.filter(user=user).count(), 1)

    def test_signal_does_not_duplicate_patient(self):
        user = self._create_user('signal@test.com')
        profile = Utilisateur.objects.get(user=user)
        profile.role = 'user'
        profile.nom = 'Signal Test'
        profile.save()
        ensure_patient_for_user(user, nom='Signal Test')
        self.assertEqual(Patient.objects.filter(user=user).count(), 1)
        self.assertEqual(Compte.objects.filter(patient__user=user).count(), 1)

    def test_concurrent_patient_creation(self):
        """Deux threads : un seul Patient créé pour le même user."""
        user = self._create_user('race@test.com')
        Utilisateur.objects.filter(user=user).update(role='user')
        results = []
        errors = []

        def worker():
            try:
                connection.close()
                results.append(ensure_patient_for_user(user, nom='Race'))
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        self.assertEqual(errors, [], errors)
        self.assertEqual(len(results), 8)
        ids = {p.id for p in results}
        self.assertEqual(len(ids), 1)
        self.assertEqual(Patient.objects.filter(user=user).count(), 1)

    def test_cannot_create_duplicate_user_patient(self):
        user = self._create_user('dup@test.com')
        ensure_patient_for_user(user)
        with self.assertRaises(IntegrityError):
            Patient.objects.create(user=user, nom='Doublon')
