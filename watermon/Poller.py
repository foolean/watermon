'''
Poller - Module for polling a Chandler Systems, Inc. Smart Valve
'''

# Import standard modules
import datetime
import logging
import signal
import time
import threading

# Import our modules
import watermon

# Set our version
__version__ = '1.0.0'

# Establish our module-level logger
LOG = logging.getLogger(__name__)


class Poller:
    '''
    Class to poll a Chandler Systems, Inc. Smart Valve

    Received data is then processed and written to a database, which can
    then be visualized.
    '''
    def __init__(self, device=None, calibration_factor=1, db_config=None, onetime=False):
        '''
        Class constructor

        Arguments:
            device
                Bluetooth (BLE) MAC address of the meter

            calibration_factor
                We're attempting to determine the gallons used based on flow
                rates read every second.  The reality is that we don't really
                read every send and thus are sometimes off.  It would be more
                accurate to read the flow rate several times per second but
                the meter can't really handle that.  The calibration_factor
                is an attempt to compensate for this inconsistency so that
                longer term monitoring eventually normalizes to a more accurate
                value.

            db_config
                Dictionary of database connection details

                database
                host
                port
                user
                password
        '''
        self._address = device
        self._calibration_factor = float(calibration_factor)
        self._total_gallons_used = 0
        self._data = {}
        self._active = False
        self._changed = []
        self._meter = None
        self._sql = None
        self._onetime = onetime

        LOG.info('Connecting to meter')
        self._meter = watermon.CSMeter(address=device)

        LOG.info('Connecting to database')
        self._sql = watermon.Postgres(**db_config)

        self._prep_realtime()


    def __del__(self):
        '''
        Class destructor
        '''
        self.close()


    def _signal_handler(self, signalnum, frame):
        '''
        Helper function to exit cleanly when SIGINT is caught
        '''
        del frame

        # Create a list of signale names so we can convert
        # the incoming signal number to its readable name.
        # (doing it this way is more portable)
        signals = dict((k, v) for v, k in reversed(sorted(signal.__dict__.items())) if v.startswith('SIG') and not v.startswith('SIG_'))

        LOG.warning('caught signal "%s"', signals[signalnum])
        self._active = False
        self.__del__()


    def _set_value(self, field, value):
        '''
        Set a value in the main data dictionary if it has changed

        Arguments:
            field       field to be updated
            value       value to be set
        '''
        changed = False

        # determine if the field doesn't exist or has changed
        if field not in self._data:
            changed = True
        elif self._data[field] != value:
            changed = True

        # set the value and add the field to the list of changed fields
        if changed is True:
            self._data[field] = value
            if field not in self._changed:
                self._changed.append(field)


    def _insert(self):
        '''
        Insert the timeseries data into the database
        '''
        # Get the current timestamp
        timestamp = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S.%f')

        # Assemble the SQL command
        sql_command = f"INSERT INTO watermon (time_utc, device, total_gallons_used) VALUES ('{timestamp}', '{self._address}', {self._total_gallons_used});"

        # Execute the SQL command
        LOG.info(sql_command)
        self._sql.execute(sql_command)


    def _update(self):
        '''
        Update the realtime data in the database
        '''
        # Don't bother if nothing has changed
        if len(self._changed) == 0:
            LOG.debug('no changes, skipping update')
            return

        LOG.debug('changes available ...')

        # Get the current timestamp
        timestamp = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S.%f')

        # Get a copy of the data
        # (not sure if this is really neccessary or useful)
        data = self._data.copy()

        # Ensure the time_of_day_on_unit and regeneration_time values are
        # quoted for when the SQL command is assembled.
        #   There's probably a better way to do this
        data['time_of_day_on_unit'] = f"'{data['time_of_day_on_unit']}'"
        data['regeneration_time'] = f"'{data['regeneration_time']}'"

        data['state'] = f"'{data['state']}'"
        data['step'] = f"'{data['step']}'"

        # Get the list of changed values
        values = [data[key] for key in self._changed]

        # Assemble the SQl command
        # pylint: disable=consider-using-f-string
        sql_template = "UPDATE watermon_realtime SET last_update = '{}', {} WHERE device = '{}';".format(timestamp, ', '.join("%s = {}" % key for key in self._changed), self._address)
        sql_command = sql_template.format(*values)
        # pylint: enable=consider-using-f-string

        # Execute the SQL command
        LOG.info(sql_command)
        self._sql.execute(sql_command)


    def _prep_realtime(self):
        '''
        Attempt to insert the device into the realtime table on the database.
        This ensures the record for this device exists when we attempt to
        update the realtime data later.
        '''
        # Get the current timestamp
        timestamp = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S.%f')

        # Assemble the SQL command
        sql_command = f"INSERT INTO watermon_realtime (last_update, device) VALUES ('{timestamp}', '{self._address}') ON CONFLICT (device) DO NOTHING;"

        # Execute the SQL command
        LOG.debug(sql_command)
        self._sql.execute(sql_command)


    def start(self):
        '''
        Start the polling cycle
        '''
        # Trap SIGINT
        signal.signal(signal.SIGINT, self._signal_handler)

        now = datetime.datetime.now()
        prev_hour = now.hour
        prev_minute = now.minute

        # Set ourselves as active
        self._active = True

        # Start the polling loop
        LOG.info('Starting poller loop')
        while self._active is True:

            LOG.debug('loop: %i active threads', threading.active_count())
            for thread in threading.enumerate():
                LOG.debug('loop: .... [%s]', thread.name)

            LOG.debug('loop: getting current date')
            now = datetime.datetime.now()

            # Get the meter's dashboard data
            LOG.debug('loop: getting dashboard')
            data = {}
            data = self._meter.get_dashboard()

            # Continue the loop if we didn't get anything
            if not data:
                LOG.error('No data received')
                continue

            # Calculate the total gallons used
            # We do this by dividing the current water flow by 60 since we're
            # polling every second for realtime data and every minute for the
            # timeseries data.
            LOG.debug('loop: computing total gallons used')
            if 'current_water_flow' in data:
                self._total_gallons_used = self._total_gallons_used + ((data['current_water_flow'] / 60) * self._calibration_factor)
                data['total_gallons_used'] = self._total_gallons_used
            else:
                LOG.error('current_water_flow not found in received data')

            # Reconnect if the hour has changed
            LOG.debug('loop: checking for hour change')
            if now.hour != prev_hour:
                # Testing: attempting to prove a disconnect/reconnect paradigm
                LOG.debug('loop: hour change, attempting reconnection')
                self._meter.reconnect(True)
                self._sql.connect()
                #self._meter.disconnect()
                #LOG.debug('loop: .... waiting for 5 seconds')
                #time.sleep(5)
                #self._meter.connect()
                #self._meter.mtu()
                #self._meter.subscribe()

                # Update the hour tracker
                prev_hour = now.hour

            # Write the timeseries data if we're at the top of the minute
            LOG.debug('loop: checking for minute change')
            if now.minute != prev_minute or self._onetime is True:

                # Add the total gallons used to the timeseries table
                LOG.debug('loop: inserting timeseries data')
                self._insert()

                # Get the rest of the data
                LOG.debug('loop: getting advanced settings data')
                data.update(self._meter.get_settings())
                LOG.debug('loop: getting status/history data')
                data.update(self._meter.get_history())

                # Update the minute tracker
                prev_minute = now.minute

            # Update the data
            LOG.debug('loop: updating the data object')
            for key, value in data.items():
                self._set_value(key, value)

            LOG.debug('loop: updating the realtime data')
            self._update()

            # Reset the list of changed elements
            LOG.debug('loop: clearing the list of changed items')
            self._changed.clear()

            if self._onetime is True:
                self._active = False
            else:
                LOG.debug('loop: waiting 1 second')
                time.sleep(1)
                LOG.debug('loop: looping back to top')


    def close(self):
        '''
        Close our connections
        '''
        if self._meter is not None:
            LOG.info('Disconnecting from meter')
            self._meter.disconnect()

        if self._sql is not None:
            LOG.info('Closeing database')
            self._sql.close()
