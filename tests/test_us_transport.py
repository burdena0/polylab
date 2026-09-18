import unittest,tempfile
from polylab.us_transport import reserve,cooldown,CoolingDown

class USTransportTests(unittest.TestCase):
    def test_connections_share_slots_and_do_not_shorten_cooldown(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(reserve(root,100),0)
            self.assertEqual(reserve(root,100),3)
            cooldown(root,900,100);cooldown(root,300,101)
            with self.assertRaises(CoolingDown) as caught:reserve(root,900)
            self.assertEqual(caught.exception.seconds,100)
            self.assertEqual(reserve(root,1001),0)
