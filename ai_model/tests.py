from django.test import TestCase
from django.urls import reverse

class BasicTests(TestCase):
    def test_homepage(self):
        response = self.client.get(reverse(''))  # urls.py’deki ana sayfa ismi neyse onu yaz
        self.assertEqual(response.status_code, 200)

    def test_sample_logic(self):
        self.assertEqual(2 * 2, 4)

# Create your tests here.
