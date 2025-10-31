import sqlite3
import queue
import threading
import os


class SQLitePool:
    """A very small sqlite connection pool.

    Each connection is created with check_same_thread=False and WAL mode enabled
    to improve concurrency for reads. The pool hands out connections wrapped in
    a PooledConnection which returns the underlying connection back to the pool
    when .close() is called — this keeps the rest of the code unchanged.
    """

    def __init__(self, db_path: str, maxsize: int = 5, timeout: int = 5):
        self.db_path = db_path
        self.maxsize = maxsize
        self.timeout = timeout
        self._pool = queue.Queue(maxsize)
        self._lock = threading.Lock()

        # Pre-create one connection; others are lazy-created to avoid IO at import
        conn = self._create_connection()
        self._pool.put(conn)

    def _create_connection(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=self.timeout)
        try:
            conn.execute('PRAGMA journal_mode=WAL')
        except Exception:
            pass
        # keep row access by index compatible with existing code
        conn.row_factory = None
        return conn

    def getconn(self):
        try:
            conn = self._pool.get(block=True, timeout=self.timeout)
            return PooledConnection(conn, self)
        except Exception:
            # pool empty, try to create a new connection if capacity allows
            with self._lock:
                try:
                    conn = self._create_connection()
                    return PooledConnection(conn, self)
                except Exception:
                    raise

    def putconn(self, conn):
        try:
            # put back into pool (if pool is full, close connection)
            self._pool.put(conn, block=False)
        except Exception:
            try:
                conn.close()
            except Exception:
                pass


class PooledConnection:
    """Wraps sqlite3.Connection and returns to pool when closed."""

    def __init__(self, conn, pool: SQLitePool):
        self._conn = conn
        self._pool = pool

    def cursor(self):
        return self._conn.cursor()

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def execute(self, *args, **kwargs):
        return self._conn.execute(*args, **kwargs)

    def executemany(self, *args, **kwargs):
        return self._conn.executemany(*args, **kwargs)

    def close(self):
        # Return the raw connection to the pool for reuse
        self._pool.putconn(self._conn)

    # Support use as context manager
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
