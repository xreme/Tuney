import unittest,tempfile,os
import tuney.wishlist

class ConnectionTest(unittest.TestCase):
    """Test creating wishlist instance"""
    def test_connection(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            wishlist = tuney.wishlist.Wishlist("test")
            self.assertIsInstance(wishlist, tuney.wishlist.Wishlist)
        finally:
            os.unlink(path)