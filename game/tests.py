import datetime
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Hunt, Step, PlayerProgress, PlayerStep
from openpyxl import Workbook


class TreasureHuntFlowTests(TestCase):
    def setUp(self):
        # Isoler les médias générés pendant les tests (QR codes) pour ne pas polluer le repo.
        self.media_tmp = TemporaryDirectory()
        self.addCleanup(self.media_tmp.cleanup)
        self.override_media = override_settings(MEDIA_ROOT=self.media_tmp.name)
        self.override_media.enable()
        self.addCleanup(self.override_media.disable)

        self.user = User.objects.create_user(username="alice", password="pass12345")
        self.hunt = Hunt.objects.create(
            title="Test Hunt",
            description="A simple test hunt",
            start_clue="Start here",
        )
        self.step1 = Step.objects.create(
            hunt=self.hunt,
            order=1,
            name="First stop",
            clue_text="Go to the next place",
        )
        self.step2 = Step.objects.create(
            hunt=self.hunt,
            order=2,
            name="Second stop",
            clue_text="Finish line",
        )
        self.client.login(username="alice", password="pass12345")

    def test_start_hunt_creates_progress(self):
        response = self.client.get(
            reverse("game:start_hunt", args=[self.hunt.id]), follow=False
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url, reverse("game:current_step", args=[self.hunt.id])
        )

        progress = PlayerProgress.objects.get(user=self.user, hunt=self.hunt)
        self.assertIsNone(progress.current_step)
        self.assertEqual(progress.total_points, 0)
        self.assertFalse(progress.completed)

    def test_current_step_shows_start_clue(self):
        self.client.get(reverse("game:start_hunt", args=[self.hunt.id]))
        response = self.client.get(reverse("game:current_step", args=[self.hunt.id]))

        self.assertContains(response, "Start here")
        self.assertContains(response, "Étape 1")

    def test_scan_qr_sequence_updates_progress_and_score(self):
        base_time = timezone.make_aware(datetime.datetime(2025, 1, 1, 12, 0, 0))
        later_time = base_time + datetime.timedelta(minutes=30)

        with patch("game.views.timezone.now", return_value=base_time):
            self.client.get(reverse("game:scan_qr", args=[self.step1.secret_token]))

        PlayerProgress.objects.filter(user=self.user, hunt=self.hunt).update(
            updated_at=base_time
        )

        with patch("game.views.timezone.now", return_value=later_time):
            self.client.get(reverse("game:scan_qr", args=[self.step2.secret_token]))

        progress = PlayerProgress.objects.get(user=self.user, hunt=self.hunt)
        progress.refresh_from_db()
        self.assertEqual(progress.current_step, self.step2)
        self.assertTrue(progress.completed)
        self.assertEqual(progress.total_points, 77)

        steps = PlayerStep.objects.filter(progress=progress).order_by("step__order")
        self.assertEqual(steps.count(), 2)
        self.assertEqual(steps[1].points_earned, 77)
        self.assertEqual(steps[1].time_taken_seconds, 1800)

    def test_scan_qr_wrong_order_does_not_advance(self):
        response = self.client.get(
            reverse("game:scan_qr", args=[self.step2.secret_token])
        )

        self.assertEqual(response.status_code, 302)
        progress = PlayerProgress.objects.get(user=self.user, hunt=self.hunt)
        self.assertIsNone(progress.current_step)
        self.assertEqual(progress.total_points, 0)

    def test_scan_qr_with_extra_suffix_still_works(self):
        # Simule une URL scannée avec un segment supplémentaire (ex: /name=scanQR)
        url = f"/scan/{self.step1.secret_token}/name=scanQR"
        response = self.client.get(url, follow=True)

        self.assertTrue(response.redirect_chain, f"Redirect chain: {response.redirect_chain}")
        self.assertNotIn("/accounts/login", response.redirect_chain[-1][0] if response.redirect_chain else "")
        self.assertTrue(
            PlayerProgress.objects.filter(user=self.user, hunt=self.hunt).exists(),
            f"Redirect chain: {response.redirect_chain}, final path: {response.request.get('PATH_INFO')}, status: {response.status_code}"
        )
        progress = PlayerProgress.objects.get(user=self.user, hunt=self.hunt)
        self.assertEqual(progress.current_step, self.step1)

    def test_scan_qr_with_legacy_game_prefix(self):
        url = f"/game/scan/{self.step1.secret_token}/"
        response = self.client.get(url, follow=True)

        self.assertTrue(response.redirect_chain, f"Redirect chain: {response.redirect_chain}")
        progress = PlayerProgress.objects.get(user=self.user, hunt=self.hunt)
        self.assertEqual(progress.current_step, self.step1)

    def test_qr_code_generation_uses_site_base_url(self):
        capture = {}

        class DummyQR:
            def save(self, buffer, format='PNG'):
                buffer.write(b'dummy')  # Génère un contenu minimal pour l'image

        def fake_make(data):
            capture['data'] = data
            return DummyQR()

        with override_settings(SITE_BASE_URL="https://game.laviedesza.fr"), patch(
            "game.models.qrcode.make", side_effect=fake_make
        ):
            step = Step.objects.create(
                hunt=self.hunt,
                order=3,
                name="Third stop",
                clue_text="Almost done",
            )

        expected_url = f"https://game.laviedesza.fr{reverse('game:scan_qr', args=[step.secret_token])}"
        self.assertEqual(capture.get("data"), expected_url)
        self.assertTrue(step.qr_code.name)

    def test_import_hunt_from_xlsx(self):
        with TemporaryDirectory() as tmp:
            path = f"{tmp}/hunt.xlsx"
            wb = Workbook()
            ws = wb.active
            ws.append(["Import Hunt", "Description import", "First clue"])
            ws.append([1, "Spot A", "Go to B"])
            ws.append([2, "Spot B", "Go to C"])
            wb.save(path)

            call_command("import_hunt_xlsx", path)
            import os
            import gc
            gc.collect()
            os.remove(path)

        hunt = Hunt.objects.get(title="Import Hunt")
        steps = list(hunt.steps.order_by("order"))
        self.assertEqual(len(steps), 2)
        self.assertEqual(steps[0].name, "Spot A")
        self.assertEqual(steps[1].clue_text, "Go to C")
