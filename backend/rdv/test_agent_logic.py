"""Tests de la logique agent (dashboard, file d'attente, appels)."""
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.utils import timezone

from .forms import cabinet_local_today, cabinet_day_datetime_bounds
from .models import Rendez_vous, ensure_patient_for_user


class AgentWorkflowTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.agent = User.objects.get(username='agent@agent.com')
        self.patient = User.objects.create_user(
            username='patient_agent_test',
            email='patient_agent_test@test.com',
            password='password123',
        )
        ensure_patient_for_user(self.patient, nom='Patient Test Agent')
        today = cabinet_local_today()
        start_day, _ = cabinet_day_datetime_bounds(today)
        self.rdv_today = Rendez_vous.objects.create(
            titre='Consultation test',
            description='Test agent',
            date=start_day + timedelta(hours=10),
            utilisateur=self.patient,
            status='pending',
            priority='normal',
        )
        self.rdv_future = Rendez_vous.objects.create(
            titre='RDV futur',
            description='Test',
            date=start_day + timedelta(days=5),
            utilisateur=self.patient,
            status='pending',
            priority='urgent',
        )

    def _login_agent(self):
        self.client.force_login(self.agent)

    def test_agent_login_redirects_to_dashboard(self):
        self.client.logout()
        response = self.client.post('/login/', {
            'email': 'agent@agent.com',
            'password': 'agent123',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/agent/dashboard/')

    def test_admin_login_redirects_to_admin(self):
        self.client.logout()
        response = self.client.post('/login/', {
            'email': 'admin@admin.com',
            'password': 'admin123',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/admin/')

    def test_admin_cannot_access_agent_dashboard(self):
        admin = User.objects.get(username='admin@admin.com')
        self.client.force_login(admin)
        response = self.client.get('/agent/dashboard/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/admin/')

    def test_admin_cannot_access_agent_file_attente(self):
        admin = User.objects.get(username='admin@admin.com')
        self.client.force_login(admin)
        response = self.client.get('/agent/file-dattente/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/admin/')

    def test_patient_cannot_access_agent_dashboard(self):
        self.client.force_login(self.patient)
        response = self.client.get('/agent/dashboard/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/extranet/')

    def test_agent_dashboard_shows_today_rdv(self):
        self._login_agent()
        response = self.client.get('/agent/dashboard/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Consultation test')
        self.assertContains(response, 'Patient Test Agent')

    def test_agent_file_attente_lists_pending(self):
        self._login_agent()
        response = self.client.get('/agent/file-dattente/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Patient Test Agent')
        self.assertContains(response, 'Appeler le patient')

    def test_appeler_prochain_marks_confirmed_and_removes_from_queue(self):
        self._login_agent()
        before_pending = Rendez_vous.objects.filter(status='pending').count()
        response = self.client.post('/agent/appeler-prochain/')
        self.assertEqual(response.status_code, 302)
        self.rdv_today.refresh_from_db()
        self.assertEqual(self.rdv_today.status, 'confirmed')
        after_pending = Rendez_vous.objects.filter(status='pending').count()
        self.assertEqual(after_pending, before_pending - 1)

    def test_valider_rejects_pending(self):
        self._login_agent()
        response = self.client.post(f'/agent/rdv/{self.rdv_today.pk}/valider/')
        self.assertEqual(response.status_code, 302)
        self.rdv_today.refresh_from_db()
        self.assertEqual(self.rdv_today.status, 'pending')

    def test_valider_after_appeler_marks_done(self):
        self._login_agent()
        self.client.post(f'/agent/rdv/{self.rdv_today.pk}/appeler/')
        self.rdv_today.refresh_from_db()
        self.assertEqual(self.rdv_today.status, 'confirmed')
        response = self.client.post(f'/agent/rdv/{self.rdv_today.pk}/valider/')
        self.assertEqual(response.status_code, 302)
        self.rdv_today.refresh_from_db()
        self.assertEqual(self.rdv_today.status, 'done')

    def test_agent_redirected_from_patient_extranet(self):
        self._login_agent()
        response = self.client.get('/extranet/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/agent/dashboard/')

    def test_prochain_prioritizes_today_over_future(self):
        self._login_agent()
        prochain = Rendez_vous.objects.next_in_queue_agent_global()
        self.assertEqual(prochain.pk, self.rdv_today.pk)

    def test_dashboard_stats_today_vs_total_pending(self):
        """En attente aujourd'hui ≠ total si des RDV pending existent à d'autres dates."""
        self._login_agent()
        response = self.client.get('/agent/dashboard/')
        self.assertEqual(response.status_code, 200)
        ctx = response.context
        self.assertEqual(ctx['en_attente_aujourdhui_count'], 1)
        self.assertEqual(ctx['en_attente_total_count'], 2)
        self.assertEqual(ctx['count_rdv_jour'], 1)
        self.assertEqual(len(list(ctx['rdv_du_jour_list'])), 1)

    def test_dashboard_rdv_jour_excludes_cancelled(self):
        self.rdv_today.status = 'cancelled'
        self.rdv_today.save()
        self._login_agent()
        response = self.client.get('/agent/dashboard/')
        self.assertEqual(response.context['count_rdv_jour'], 0)
        self.assertEqual(response.context['en_attente_aujourdhui_count'], 0)

    def test_dashboard_shows_date_reference(self):
        self._login_agent()
        today = cabinet_local_today()
        label = today.strftime('%d/%m/%Y')
        response = self.client.get('/agent/dashboard/')
        self.assertContains(response, label)
        self.assertContains(response, 'En attente aujourd')
        self.assertContains(response, 'En attente total')
        self.assertContains(response, 'Toutes dates')

    def test_dashboard_appelles_aujourdhui_matches_today_confirmed(self):
        self.rdv_today.status = 'confirmed'
        self.rdv_today.save()
        self._login_agent()
        response = self.client.get('/agent/dashboard/')
        self.assertEqual(response.context['appelles_aujourdhui_count'], 1)
        self.assertEqual(response.context['count_rdv_jour'], 1)

    def test_appeler_future_pending_rejected(self):
        self._login_agent()
        response = self.client.post(f'/agent/rdv/{self.rdv_future.pk}/appeler/')
        self.assertEqual(response.status_code, 302)
        self.rdv_future.refresh_from_db()
        self.assertEqual(self.rdv_future.status, 'pending')

    def test_valider_future_confirmed_rejected(self):
        self.rdv_future.status = 'confirmed'
        self.rdv_future.save()
        self._login_agent()
        response = self.client.post(f'/agent/rdv/{self.rdv_future.pk}/valider/')
        self.assertEqual(response.status_code, 302)
        self.rdv_future.refresh_from_db()
        self.assertEqual(self.rdv_future.status, 'confirmed')

    def test_valider_before_appointment_time_rejected(self):
        self.rdv_today.status = 'confirmed'
        self.rdv_today.date = timezone.now() + timedelta(hours=3)
        self.rdv_today.save()
        self._login_agent()
        response = self.client.post(f'/agent/rdv/{self.rdv_today.pk}/valider/')
        self.rdv_today.refresh_from_db()
        self.assertEqual(self.rdv_today.status, 'confirmed')

    def test_valider_after_appointment_time_succeeds(self):
        self.rdv_today.status = 'confirmed'
        self.rdv_today.date = timezone.now() - timedelta(minutes=15)
        self.rdv_today.save()
        self._login_agent()
        response = self.client.post(f'/agent/rdv/{self.rdv_today.pk}/valider/')
        self.rdv_today.refresh_from_db()
        self.assertEqual(self.rdv_today.status, 'done')

    def test_patient_sees_called_status_in_file(self):
        self.rdv_today.status = 'confirmed'
        self.rdv_today.save()
        self.client.force_login(self.patient)
        response = self.client.get('/file-dattente/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'appelé')
        self.assertContains(response, 'Présentez-vous au cabinet')

    def test_called_patient_still_on_agent_file(self):
        self.rdv_today.status = 'confirmed'
        self.rdv_today.save()
        self._login_agent()
        response = self.client.get('/agent/file-dattente/')
        self.assertContains(response, 'Appelés')
        self.assertContains(response, 'Confirmer passage chez le médecin')

    def test_agent_button_labels_harmonized(self):
        """Même action backend = même libellé ; pas de doublon appeler-prochain sur le dashboard."""
        today = cabinet_local_today()
        start_day, _ = cabinet_day_datetime_bounds(today)
        Rendez_vous.objects.create(
            titre='RDV déjà appelé',
            description='Test libellés boutons',
            date=start_day + timedelta(hours=9),
            utilisateur=self.patient,
            status='confirmed',
            priority='normal',
        )
        self._login_agent()
        dashboard = self.client.get('/agent/dashboard/')
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(
            dashboard.content.decode().count('Appeler le patient suivant'),
            1,
            'Un seul bouton « Appeler le patient suivant » (carte prochain).',
        )
        self.assertNotContains(dashboard, 'Appeler ce patient')
        self.assertContains(dashboard, 'Appeler le patient')
        self.assertContains(dashboard, 'Confirmer passage chez le médecin')
        self.assertNotContains(dashboard, '>Valider<')

        file_attente = self.client.get('/agent/file-dattente/')
        self.assertEqual(file_attente.status_code, 200)
        self.assertContains(file_attente, 'Appeler le patient')
        self.assertContains(file_attente, 'Confirmer passage chez le médecin')
        self.assertNotContains(file_attente, 'Appeler le patient suivant')
