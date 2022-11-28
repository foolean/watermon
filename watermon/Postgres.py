'''
Module for working with a postgres database
'''
# Import standard modules
import logging

# Import third-party modules
import psycopg2

# Set our version
__version__ = '1.0.0'

# Establish our module-level logger
LOG = logging.getLogger(__name__)


class Postgres:
    '''
    Class for working with a postgres database

    Arguments:
        database    Name of the database to use
        host        Hostname or IP address of the database server
        port        TCP port of the database service
        user        Username used to authenticate
        password    Password used to authenticate
    '''
    #pylint: disable=too-many-arguments
    def __init__(self, database='watermon', host='localhost', port=5432, user='watermon', password='watermon'):
        '''
        Class constructor
        '''
        # Our database configuration
        self._config = {}
        self._config['database'] = database
        self._config['host'] = host
        self._config['port'] = port
        self._config['user'] = user
        self._config['password'] = password

        # Our database and cursor objects
        self._db = None
        self._cursor = None

        # Connect to the database
        self.connect()
    #pylint: enable=too-many-arguments


    def __del__(self):
        '''
        Class destructor
        '''
        # Close the connection to our database
        self.close()


    def connect(self):
        '''
        Connect to the remote database
        '''
        if isinstance(self._db, psycopg2.extensions.connection):
            self.close()

        if not isinstance(self._db, psycopg2.extensions.connection):
            LOG.info('Connecting to database %s on %s:%s as %s',
                     self._config['database'],
                     self._config['host'],
                     self._config['port'],
                     self._config['user'])
            try:
                self._db = psycopg2.connect(**self._config, connect_timeout=3, options='-c statement_timeout=5000')
            except (psycopg2.OperationalError, psycopg2.InterfaceError) as err:
                LOG.error('Unable to connect to database %s on %s:%s as %s: %s: %s',
                              self._config['database'],
                              self._config['host'],
                              self._config['port'],
                              self._config['user'],
                              type(err).__name__,
                              err)
                raise
            self._db.autocommit = True
            self._cursor = self._db.cursor()


    def close(self):
        '''
        Close the connection to the database
        '''
        if isinstance(self._db, psycopg2.extensions.connection):
            LOG.info('Closing database %s on %s:%s',
                     self._config['database'],
                     self._config['host'],
                     self._config['port'])
            try:
                self._db.close()
                self._db = None
                self._cursor = None
            except (psycopg2.OperationalError, psycopg2.InterfaceError) as err:
                LOG.error('Unable to close database %s on %s:%s: %s: %s',
                              self._config['database'],
                              self._config['host'],
                              self._config['port'],
                              type(err).__name__,
                              err)


    def execute(self, command):
        '''
        Execute a SQL command

        Arguments:
            command     The SQL command to be executed
        '''
        LOG.debug("Executing SQL command:\n%s\n", command)
        try:
            self._cursor.execute(command)
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as err:
            LOG.error('Unable to execute command: %s: %s', type(err).__name__, err)
            self.close()
            self.connect()

        LOG.debug('Committing the transaction')
        try:
            self._db.commit()
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as err:
            LOG.error('Unable to commit transaction: %s: %s', type(err).__name__, err)
