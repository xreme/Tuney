import os
import sqlite3
import tempfile
import threading
import unittest

from tuney import dbservice
from tuney.wishlist import Wishlist


class DatabaseServiceTest(unittest.TestCase):

    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)

    def tearDown(self):
        dbservice.shutdown(self.path)
        os.unlink(self.path)

    def test_one_service_per_database(self):
        self.assertIs(dbservice.service(self.path), dbservice.service(self.path))

    def test_work_runs_on_the_calling_thread(self):
        service = dbservice.service(self.path)
        ran_on = service.read(lambda _: threading.current_thread())
        self.assertIs(ran_on, threading.current_thread())

    def test_each_thread_gets_its_own_connection(self):
        service = dbservice.service(self.path)
        mine = service.read(lambda connection: connection)
        theirs: list = []
        thread = threading.Thread(
            target=lambda: theirs.append(service.read(lambda c: c)))
        thread.start()
        thread.join()
        self.assertIsNot(mine, theirs[0])

    def test_result_comes_back_to_the_caller(self):
        service = dbservice.service(self.path)
        self.assertEqual(service.read(lambda c: c.execute("SELECT 7").fetchone()[0]), 7)

    def test_failing_work_raises_in_the_caller_and_rolls_back(self):
        service = dbservice.service(self.path)
        service.write(lambda c: c.execute("CREATE TABLE t(x INTEGER PRIMARY KEY)"))

        def half_written(connection):
            connection.execute("INSERT INTO t VALUES (1)")
            raise sqlite3.IntegrityError("boom")

        with self.assertRaises(sqlite3.IntegrityError):
            service.write(half_written)
        # A botched transaction can't leak into the next write on this thread.
        self.assertEqual(service.read(lambda c: c.execute("SELECT count(*) FROM t").fetchone()[0]), 0)

    def test_nested_write_joins_the_open_transaction(self):
        """Work that calls back into the data layer — reconcile does — must not
        deadlock on the write lock or open a second transaction."""
        service = dbservice.service(self.path)
        wishlist = Wishlist(self.path)
        result = service.write(lambda _: wishlist.add_item(artist="A", title="B"))
        self.assertEqual(wishlist.get_item(result)["title"], "B")

    def test_nested_write_rolls_back_with_the_outer_one(self):
        service = dbservice.service(self.path)
        wishlist = Wishlist(self.path)

        def outer(_):
            wishlist.add_item(artist="A", title="B")
            raise sqlite3.IntegrityError("boom")

        with self.assertRaises(sqlite3.IntegrityError):
            service.write(outer)
        self.assertEqual(wishlist.all_items(), [])

    def test_reads_run_while_a_write_is_open(self):
        """The point of dropping the queue: a slow write must not stall the
        TUI's reads."""
        service = dbservice.service(self.path)
        wishlist = Wishlist(self.path)
        wishlist.add_item(artist="A", title="B")
        read_through = threading.Event()

        def slow_write(_):
            thread = threading.Thread(
                target=lambda: read_through.set() if wishlist.all_items() else None)
            thread.start()
            thread.join(timeout=5)

        service.write(slow_write)
        self.assertTrue(read_through.is_set())

    def test_concurrent_writers_all_commit(self):
        """The failure this module exists for: concurrent writers used to lose
        rows to 'database is locked'."""
        wishlist = Wishlist(self.path)
        errors: list[BaseException] = []
        barrier = threading.Barrier(8)

        def add(n: int) -> None:
            try:
                barrier.wait()
                for i in range(10):
                    wishlist.add_item(artist=f"A{n}", title=f"T{i}")
            except BaseException as error:  # noqa: BLE001 - reported below
                errors.append(error)

        threads = [threading.Thread(target=add, args=(n,)) for n in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(errors, [])
        self.assertEqual(len(wishlist.all_items()), 80)

    def test_wal_is_enabled_so_other_connections_can_read_during_writes(self):
        dbservice.service(self.path).read(lambda _: None)
        with sqlite3.connect(self.path) as other:
            mode = other.execute("PRAGMA journal_mode").fetchone()[0]
        self.assertEqual(mode.lower(), "wal")

    def test_closed_service_refuses_work_and_reopens_on_demand(self):
        service = dbservice.service(self.path)
        dbservice.shutdown(self.path)
        with self.assertRaises(sqlite3.ProgrammingError):
            service.read(lambda c: c.execute("SELECT 1"))
        self.assertIsNot(dbservice.service(self.path), service)


if __name__ == "__main__":
    unittest.main()
