import json
import threading
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import IntegrityError, connection
from django.test import Client, TestCase, TransactionTestCase
from django.utils import timezone

from .models import Patient, Compte, Utilisateur, Rendez_vous, ensure_patient_for_user
from .forms import cabinet_local_today, cabinet_day_datetime_bounds


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


class PatientDataIsolationTests(TestCase):
    """Chaque patient ne voit que ses propres données."""

    def setUp(self):
        self.client = Client()
        self.patient1 = User.objects.create_user(
            username='patient1',
            email='patient1@test.com',
            password='password123',
        )
        self.patient2 = User.objects.create_user(
            username='patient2',
            email='patient2@test.com',
            password='password123',
        )
        ensure_patient_for_user(self.patient1, nom='Patient Un')
        ensure_patient_for_user(self.patient2, nom='Patient Deux')
        start_day, _ = cabinet_day_datetime_bounds(cabinet_local_today())
        self.rdv_p1 = Rendez_vous.objects.create(
            titre='RDV secret patient1',
            description='Consultation',
            date=start_day + timedelta(hours=10),
            utilisateur=self.patient1,
            status='pending',
        )
        self.rdv_p2 = Rendez_vous.objects.create(
            titre='RDV secret patient2',
            description='Consultation',
            date=start_day + timedelta(hours=11),
            utilisateur=self.patient2,
            status='pending',
        )

    def _login(self, user):
        self.client.force_login(user)

    def test_patient_list_shows_only_own_rdvs(self):
        self._login(self.patient1)
        response = self.client.get('/mes-rendez-vous/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'RDV secret patient1')

        self.client.logout()
        self._login(self.patient2)
        response = self.client.get('/mes-rendez-vous/')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'RDV secret patient1')

    def test_patient_cannot_access_other_rdv_by_url(self):
        self._login(self.patient2)
        response = self.client.get(f'/rdv/{self.rdv_p1.pk}/modifier/')
        self.assertEqual(response.status_code, 404)

    def test_patient_cannot_cancel_other_rdv_by_url(self):
        self._login(self.patient2)
        response = self.client.post(f'/rdv/{self.rdv_p1.pk}/annuler/')
        self.assertEqual(response.status_code, 404)
        self.rdv_p1.refresh_from_db()
        self.assertEqual(self.rdv_p1.status, 'pending')

    def test_file_attente_shows_day_queue_anonymized(self):
        self._login(self.patient2)
        response = self.client.get('/file-dattente/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Patient n°1')
        self.assertContains(response, 'Patient n°2')
        self.assertContains(response, 'Vous')
        self.assertNotContains(response, 'Patient Un')
        self.assertNotContains(response, 'Patient Deux')
        self.assertNotContains(response, 'RDV secret patient1')

        self.client.logout()
        self._login(self.patient1)
        response = self.client.get('/file-dattente/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Patient n°1')
        self.assertContains(response, 'Vous')
        self.assertContains(response, 'Patient n°2')
        self.assertNotContains(response, 'RDV secret patient2')
        self.assertNotContains(response, 'Patient Deux')

    def test_file_attente_future_rdv_shows_queue_before_day(self):
        """Dès la réservation, la file du jour du RDV est visible (pas seulement le jour J)."""
        start_day, _ = cabinet_day_datetime_bounds(cabinet_local_today())
        future_day = start_day + timedelta(days=7)
        self.rdv_p1.status = 'cancelled'
        self.rdv_p1.save()
        self.rdv_p2.status = 'cancelled'
        self.rdv_p2.save()
        Rendez_vous.objects.create(
            titre='RDV futur p1',
            description='Consultation',
            date=future_day + timedelta(hours=9),
            utilisateur=self.patient1,
            status='pending',
        )
        Rendez_vous.objects.create(
            titre='RDV futur p2',
            description='Consultation',
            date=future_day + timedelta(hours=10),
            utilisateur=self.patient2,
            status='pending',
        )
        self._login(self.patient2)
        response = self.client.get('/file-dattente/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['show_queue'])
        self.assertFalse(response.context['queue_day_is_today'])
        self.assertContains(response, 'Patient n°1')
        self.assertContains(response, 'Patient n°2')
        self.assertContains(response, '1 patient devant vous')
        self.assertContains(response, 'prévisionnelle')

    def test_file_attente_three_patients_position(self):
        """Patient 3 voit les patients 1 et 2 devant lui dans la file du jour."""
        patient3 = User.objects.create_user(
            username='patient3',
            email='patient3@test.com',
            password='password123',
        )
        ensure_patient_for_user(patient3, nom='Patient Trois')
        start_day, _ = cabinet_day_datetime_bounds(cabinet_local_today())
        Rendez_vous.objects.create(
            titre='RDV patient3',
            description='Consultation',
            date=start_day + timedelta(hours=12),
            utilisateur=patient3,
            status='pending',
        )
        self._login(patient3)
        response = self.client.get('/file-dattente/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Patient n°1')
        self.assertContains(response, 'Patient n°2')
        self.assertContains(response, 'Patient n°3')
        self.assertContains(response, 'Vous')
        self.assertContains(response, '2 patients devant vous')

    def test_file_attente_called_patient_hidden_from_pending(self):
        """Une fois appelé, le patient n'apparaît plus dans la file pending des autres."""
        self.rdv_p1.status = 'confirmed'
        self.rdv_p1.save()
        self._login(self.patient2)
        response = self.client.get('/file-dattente/')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Patient n°2')
        self.assertContains(response, 'Patient n°1')
        self.assertContains(response, 'Vous')

    def test_rdv_create_assigns_current_user(self):
        self._login(self.patient2)
        before = Rendez_vous.objects.filter(utilisateur=self.patient2).count()
        Rendez_vous.objects.create(
            titre='RDV patient2',
            description='Test',
            date=timezone.now() + timedelta(days=7),
            utilisateur=self.patient2,
            status='pending',
        )
        self.assertEqual(
            Rendez_vous.objects.filter(utilisateur=self.patient2).count(),
            before + 1,
        )
        self.assertFalse(
            Rendez_vous.objects.filter(
                utilisateur=self.patient2,
                titre='RDV secret patient1',
            ).exists()
        )


class ChatbotReliabilityTests(TestCase):
    """Fiabilite du chatbot : reponses non vides, intentions coherentes."""

    def setUp(self):
        self.client = Client()

    def _chat(self, message, session_id='test_session_cb'):
        return self.client.post(
            '/api/chat/',
            data=json.dumps({'message': message, 'session_id': session_id}),
            content_type='application/json',
        )

    def test_empty_message_rejected(self):
        response = self.client.post(
            '/api/chat/',
            data=json.dumps({'message': '  ', 'session_id': 's1'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_salutation_returns_nonempty_response(self):
        response = self._chat('Bonjour')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertTrue(data['reponse'].strip())
        self.assertEqual(data['intention'], 'salutation')

    def test_salutation_typo_ssalut(self):
        response = self._chat('ssalut')
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['intention'], 'salutation')
        self.assertNotIn('pas sur de comprendre', data['reponse'].lower())

    def test_salutation_abbreviation_slt(self):
        response = self._chat('slt')
        data = response.json()
        self.assertEqual(data['intention'], 'salutation')

    def test_horaires_intention(self):
        response = self._chat('Quels sont vos horaires ?')
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['intention'], 'horaires')
        self.assertIn('Horaires', data['reponse'])
        self.assertTrue(data['reponse'].strip())

    def test_urgence_priority_over_rdv(self):
        response = self._chat('J ai une douleur urgente, je veux un rdv')
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['intention'], 'urgence')
        self.assertIn('URGENCE', data['reponse'])

    def test_tarifs_over_services_for_price_question(self):
        response = self._chat('Quel est le prix du detartrage ?')
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['intention'], 'tarifs')

    def test_prise_rdv_anonymous_redirects_login(self):
        response = self._chat('Je veux prendre un rendez-vous')
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['intention'], 'prise_rdv')
        self.assertIn('Se connecter à mon compte', data['reponse'])
        self.assertNotIn('Se connecter : /login/', data['reponse'])
        self.assertEqual(data['action'], 'redirect_login')

    def test_invalid_json_returns_400(self):
        response = self.client.post(
            '/api/chat/',
            data='not json',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_message_persisted_in_conversation(self):
        session = 'persist_test_session'
        self._chat('Bonjour', session_id=session)
        response = self.client.get(f'/api/chat/history/?session_id={session}')
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(len(data['messages']), 2)
        self.assertEqual(data['messages'][0]['role'], 'user')
        self.assertEqual(data['messages'][1]['role'], 'assistant')
        self.assertTrue(data['messages'][1]['contenu'].strip())


class AdminCompteCreateTests(TestCase):
    """Création compte agent/patient via Django admin (sans doublon profil)."""

    def setUp(self):
        self.client = Client()
        self.admin = User.objects.get(username='admin@admin.com')
        self.client.force_login(self.admin)

    def test_admin_add_agent_compte(self):
        email = 'nouvel.agent@test.com'
        response = self.client.post('/admin/rdv/utilisateur/add/', {
            'email': email,
            'password': 'Secret123!',
            'nom': 'Agent Nouveau',
            'role': 'agent',
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Utilisateur.objects.filter(user__email=email).count(), 1)
        profile = Utilisateur.objects.get(user__email=email)
        self.assertEqual(profile.role, 'agent')
        self.assertEqual(profile.nom, 'Agent Nouveau')

    def test_admin_menu_lists_comptes_and_file(self):
        response = self.client.get('/admin/')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('Comptes', content)
        self.assertIn("File d'attente", content)
        self.assertNotIn('FAQ dentaires', content)
