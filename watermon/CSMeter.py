'''
CSMeter - Module for communicating with a Chandler Systems, Inc. Smart Valve.
'''
# Import standard modules
import logging
import time
from threading import Lock

# Import 3rd party modules
import pygatt

# Set our version
__version__ = '1.0.0'

# Establish our module-level logger
LOG = logging.getLogger(__name__)


class CSMeter:
    '''
    Class to retrieve data from a Chandler Systems, Inc. Smart Valve.

    The Water Logix app has three main screens.  Dashboard, Advanced Settings,
    and Status / History.

    Unless 'raw' is specified, a dictionary with the following fields is
    returned.

        [ Dashboard ]
        average_water_usage_per_day int (see note below)
        battery_on_unit             int
        current_water_flow          float
        peak_flow_today             float
        regeneration_time           str (HH:MM AM|PM)
        soft_water_remaining        int
        time_of_day_on_unit         str (HH:MM AM|PM)
        water_hardness              int
        water_usage_today           int

        [ Advanced Settings ]
        backwash                    int
        brine_draw                  int
        brine_refill                int
        days_until_regeneration     int
        rapid_rinse                 int
        regeneration_day_override   int
        reserve_capacity            int
        resin_grains_capacity       int

        [ Status / History ]
        total_gallons_treated               int
        total_gallons_treated_since_reset   int
        total_regenerations                 int
        total_regenerations_since_reset     int


        average_water_usage_per_day:
            The Water Logix app defines average water usage per day as the
            average of the past 30, non-zero, days.

    Attributes
        address     The BLE MAC address of the Chandler Systems, Inc. SmartValve
    '''
    def __init__(self, address=None, propagate=False):
        '''
        Class constructor
        '''
        # Variables
        self._address = address

        # Buffer for handling incoming data
        self._buffer = []
        self._records = []
        self._record_id = None
        self._data_received = False
        self._command_timeout = 10

        # Lock for thread safety
        self._lock = Lock()

        # Turn off pygatt logging
        #
        # Note:
        #   consider moving this to the Poller class and
        #   follow the main program's debug/verbose flags
        logging.getLogger('pygatt').propagate = propagate

        # Create and start the adapter
        self._adapter = pygatt.GATTToolBackend()
        self._adapter.start()

        # Connect to the BLE device
        self._device = None
        self.connect()
        self.mtu()
        self.subscribe()


    def __del__(self):
        '''
        Class destructor

        This destructor ensures that the BLE connection is closed
        '''
        # Disconnect from the BLE device
        self.disconnect()

        # Stop the adapter
        self._adapter.stop()

        # Release the buffer and records
        # (this is probably unnecessary)
        self._buffer = None
        self._records = None


    def __call__(self, handle, data):
        '''
        Allow this class to serve as the callback when subscribing to
        Bluetooth Low-Energer (BLE) UART attributes

        Arguments:
            handle      handle of the BLE attribute
            data        data from the BLE attribute

        Note: The SmartValve sends data in 20-byte blocks
        '''
        LOG.debug('Received %i bytes', len(data))

        # Don't bother if there isn't any data to process
        if not data:
            return

        # Get a thread lock
        #self._lock.acquire()
        with self._lock:
            LOG.debug('lock acquired')

            # End of record characters
            # There is probably a more elegant way to detect that we
            # have received everything that the device has sent us.
            eor_char = {
                'tt0': 0x38,
                'uu0': 0x39,
                'uu1': 0x3a,
                'uu2': 0x3a,
                'vv0': 0x42,
                'vv1': 0x43,
                'ww0': 0x43,
                'ww1': 0x38,
                'ww2': 0x39,
                'ww3': 0x3a,
            }

            # List of commands.
            # These are from the perspective of the incoming record.  So
            # far it appears to be the command we sent in twice.
            # For exmaple; if we send 't', we'll get 'tt' in return.
            commands = ['tt', 'uu', 'vv', 'ww', 'xx']

            # Extract the first two characters.  We'll verify if they're
            # a command or continuation data below.
            # pylint: disable=consider-using-f-string
            command = '%c%c' % (data[0], data[1])
            # pylint: enable=consider-using-f-string

            # The third byte is the record number, which we will append
            # to the command and use it as a record id for simplification.
            #record_id = '%s%i' % (command, data[2])
            record_id = f"{command}{data[2]}"

            # Clear the buffer if we have a new command
            if command in commands:
                # If there is is data in the buffer then we'll add
                # it to the list of records now.
                if self._buffer:
                    self._records.append(list(self._buffer))
                    self._buffer.clear()

                # Save the record id in case we have more data comming
                self._record_id = record_id

            # Add the incoming data
            self._buffer.extend(data)

            # Look for a matching end-of-record character
            if self._buffer[len(self._buffer)-1] == eor_char[self._record_id]:
                # Acknowledge that we have received all of the data
                # if we have the end of the last record in the block
                if self._record_id in ['tt0', 'uu2', 'vv1', 'ww3']:
                    self._records.append(list(self._buffer))
                    self._buffer.clear()
                    self._data_received = True

            # Release our thread lock
            #self._lock.release()
        LOG.debug('lock released')

        return


    def connect(self):
        '''
        Internal function to connect to the BLE device
        '''
        # Don't do anything if we're already connected
        if isinstance(self._device, pygatt.backends.gatttool.device.GATTToolBLEDevice):
            if self.is_connected is True:
                return

        # Connect to our device
        attempt = 1
        max_retries = 3
        while attempt < max_retries:
            LOG.debug('Connecting to %s (attempt %i)', self._address, attempt)
            try:
                self._device = self._adapter.connect(
                    self._address,
                    address_type=pygatt.BLEAddressType.random,
                    timeout=5,
                    auto_reconnect=True)
            except pygatt.exceptions.NotConnectedError as error:
                if attempt <= max_retries:
                    LOG.fatal('Unable to connect to %s (attempt %i): %s', self._address, attempt, error)
                    attempt = attempt + 1
                    continue
                LOG.fatal('Unable to connect to %s after %i retries: %s', self._address, attempt - 1, error)
                raise


    def reconnect(self, force=False):
        '''
        Reconnect to the BLE device
        '''
        # Don't do anything if we're already connected
        if isinstance(self._device, pygatt.backends.gatttool.device.GATTToolBLEDevice):
            if self.is_connected is True:
                if force is True:
                    LOG.debug('Forcing disconnect from %s', self._address)
                    self.disconnect()
                return

        LOG.debug('Reconnecting to %s', self._address)
        if force is False:
            if hasattr(self._device, 'reconnect'):
                try:
                    self._device.reconnect()
                except Exception as error:
                    LOG.fatal('Unable to reconnect to %s: %s', self._address, error)
                    raise
            else:
                LOG.fatal('Unable to reconnect to %s: no reconnect() function', self._address)
                return
        else:
            LOG.debug('Waiting for 5 seconds')
            time.sleep(5)
            self.connect()
            self.mtu()
            self.subscribe()


    def is_connected(self):
        '''
        Determine if we're still connected by trying to read the
        device name characteristic
        '''
        tx_uuid = '6e400002-b5a3-f393-e0a9-e50e24dcca9e'
        try:
            self._device.char_read(tx_uuid)
        except pygatt.exceptions.NotConnectedError:
            return False

        return True


    def disconnect(self):
        '''
        Disconnect from the BLE device
        '''
        if isinstance(self._device, pygatt.backends.gatttool.device.GATTToolBLEDevice):
            LOG.debug('Disconnecting from %s', self._address)
            try:
                self._device.disconnect()
            except pygatt.exceptions.NotConnectedError:
                pass
        else:
            LOG.debug('Already disconnected from %s', self._address)


    def subscribe(self):
        '''
        Subscribe to the RX characteristic
        '''
        rx_uuid = '6e400003-b5a3-f393-e0a9-e50e24dcca9e'
        LOG.debug('Subscribing to %s', rx_uuid)
        try:
            self._device.subscribe(
                rx_uuid,
                callback=self.__call__,
                indication=False,
                wait_for_response=True
            )
        except pygatt.exceptions.NotConnectedError as err:
            LOG.error('Unable to subscribe to %s: %s', rx_uuid, err)


    def mtu(self, mtu=517):
        '''
        Set the MTU
        '''
        LOG.debug('Negotiating a MTU, offering %s', mtu)
        try:
            current_mtu = int(self._device.exchange_mtu(mtu, timeout=5))
        except pygatt.exceptions.NotConnectedError as err:
            LOG.error('Unable to negotiate MTU: %s', err)
            return None
        except pygatt.exceptions.NotificationTimeout as err:
            LOG.error('Unable to negotiate MTU: (timeout) %s', err)
            return None
        LOG.debug('MTU negotiated to %s', current_mtu)
        return current_mtu


    def _set_data_received(self, state):
        '''
        Set the data received flags in a thread safe manner.

        Arguments:
            state=[True|False]      The desired state of the flag
        '''
        with self._lock:
            LOG.debug('lock acquired')
            self._data_received = state
        LOG.debug('lock released')


    def _send_command(self, command):
        '''
        Write a command to the TX characteristic

        Arguments:
            command     The bytecode command to be sent

        Returns:
            True        The command was sent and the data is ready
            False       The command was not able to be sent
        '''
        self._set_data_received(False)
        self._records.clear()

        LOG.debug('Sending command "%s"', command)
        try:
            self._device.char_write('6e400002-b5a3-f393-e0a9-e50e24dcca9e', command, False)
        except pygatt.exceptions.NotificationTimeout as err:
            LOG.error('Unable to send command "%s": %s', command, err)
            return False

        # Wait for the processing of all incoming notifications
        # (this is a blocking operation)
        LOG.debug('Waiting %s seconds for the data to be received', self._command_timeout)
        loop_start = time.time()
        while self._data_received is False:
            if (time.time() - loop_start) >= self._command_timeout:
                LOG.error('Unable to send command "%s": timed out after %s seconds', command, self._command_timeout)
                return False
            continue

        return True


    def get_dashboard(self, include_history=False, raw=False):
        '''
        Get the Dashboard data from the Chandler Systems, Inc. Smart Valve

        Arguments:
            include_history=[True|False]
                Specify whether or not to include the histtorical data or just
                the current data.
                (default: False)

            raw=[True|False]
                Specify whether or not to return the raw data received from
                the device or parse the data and return a dictionary.
                (default: False)

        Returns:
            raw=False   A dictionary with named values
            raw=True    A list of raw bytearray records

            An empty dictionary is returned if the command doesn't succeed or
            times out.
        '''
        # Send the command to request the Dashboard data
        if self._send_command(b'u') is False:
            return {}

        # Return the raw data if requested
        if raw is True:
            return self._records

        # Initialize our data structure
        data = {}

        # Initialize our data structure
        for record in self._records:
            # pylint: disable=consider-using-f-string
            record_id = '%c%c%i' % (record[0], record[1], record[2])
            # pylint: enable=consider-using-f-string

            if record_id == 'uu0':
                data['time_of_day_on_unit'] = f"{record[3]:02d}:{record[4]:02d} {'PM' if record[5] == 1 else 'AM'}"
                data['current_water_flow'] = int.from_bytes(record[7:9], byteorder='big') / 100
                data['battery_on_unit'] = record[6]
                data['soft_water_remaining'] = int.from_bytes(record[9:11], byteorder='big')
                data['water_usage_today'] = int.from_bytes(record[11:13], byteorder='big')
                data['peak_flow_today'] = int.from_bytes(record[13:15], byteorder='big') / 100
                data['water_hardness'] = record[15]
                data['regeneration_time'] = f"{record[16]:02d}:{record[17]:02d} {'PM' if record[18] == 1 else 'AM'}"

            elif record_id == 'uu1':
                # We don't yet know how to parse this record
                # - It may be related to the various steps and
                #   and status during the regeneration process
                # Looks like this may be used during regen
                # 75-75-01-0e-03-25-00-02-01-00-00-00-00-00-00-00-00-00-00-3a
                #  u  u pg    rg mm    st ??    ??
                #
                # pg = page number
                # mr = minutes remaining (0x7f == moving to next step?)
                # ?? = (0x03 == regen, 0x0e == service)???
                # ?? = (0x01 == regen, 0x00 == service)???
                # ?? = (0x00 == regen, 0x10 == service)???
                # st = stage? (guess)
                #      00 = in-service
                #      01 = backwash
                #      02 = brine draw
                #      03 = rapid rinse
                #      04 = brine refill
                #
                # 75-75-01-0e-0e-00-00-00-00-00-10-00-00-00-00-00-00-00-00-3a
                state = int(record[4])
                step_minutes_remaining = int(record[5])
                step = int(record[7])

                steps = [
                    'In Service',
                    'Backwash',
                    'Brine draw',
                    'Rapid rinse',
                    'Brine refill',
                    'Service',
                ]

                if state == 3:
                    data['state'] = 'Regenerating'
                else:
                    data['state'] = 'In Service'

                if step_minutes_remaining == 127:
                    data['step'] = f"Moving to {steps[step+1]}"
                    data['step_minutes_remaining'] = 0
                else:
                    data['step'] = steps[step]
                    data['step_minutes_remaining'] = step_minutes_remaining

            elif record_id == 'uu2':

                # We need to multiple the values by 10 to get the final
                for index in range(4, len(record)-1):
                    record[index] = int(record[index]) * 10

                # Extract the list of gallons per day
                water_usage_gallons_per_day = list(record[3:len(record)-1])
                water_usage_gallons_per_day.reverse()

                # Calculate the average usage per day
                # The Water-Logix app defines "average" as the average over the
                # past 30 days, excluding days where the usage was 0.
                filtered = [item for item in water_usage_gallons_per_day if item != 0]
                data['average_water_usage_per_day'] = round(sum(filtered[:31]) / 30, 0)

                # Include the historical data if requested
                if include_history is True:
                    data['water_usage_gallons_per_day'] = water_usage_gallons_per_day

        # Return the data
        return data


    def get_settings(self, raw=False):
        '''
        Get the Advanced Settings data from the Chandler Systems, Inc. Smart Valve

        Arguments:
            raw=[True|False]
                Specify whether or not to return the raw data received from
                the device or parse the data and return a dictionary.
                (default: False)

        Returns:
            raw=False   A dictionary with named values
            raw=True    A list of raw bytearray records

            An empty dictionary is returned if the command doesn't succeed or
            times out.
        '''
        # Send the command to request the Advanced Settings data
        if self._send_command(b'v') is False:
            return {}

        # Return the raw data if requested
        if raw is True:
            return self._records

        # Initialize our data structure
        data = {}

        # Iterate over the records and build the dictionary
        for record in self._records:
            # pylint: disable=consider-using-f-string
            record_id = '%c%c%i' % (record[0], record[1], record[2])
            # pylint: enable=consider-using-f-string

            if record_id == 'vv0':
                data['days_until_regeneration'] = record[3]
                data['regeneration_day_override'] = record[4]
                data['reserve_capacity'] = record[5]
                data['resin_grains_capacity'] = int.from_bytes(record[6:8], byteorder='big') * 1000

            elif record_id == 'vv1':
                data['backwash'] = record[3]
                data['brine_draw'] = record[4]
                data['rapid_rinse'] = record[5]
                data['brine_refill'] = record[6]

        return data


    def get_history(self, include_history=False, raw=False):
        '''
        Get the Status / History data from the Chandler Systems, Inc. Smart Valve

        Arguments:
            include_history=[True|False]
                Specify whether or not to include the histtorical data or just
                the current data.
                (default: False)

            raw=[True|False]
                Specify whether or not to return the raw data received from
                the device or parse the data and return a dictionary.
                (default: False)

        Returns:
            raw=False   A dictionary with named values
            raw=True    A list of raw bytearray records

            An empty dictionary is returned if the command doesn't succeed or
            times out.
        '''
        # Send the command to request the Status / History data
        if self._send_command(b'w') is False:
            return {}

        # Return the raw data if requested
        if raw is True:
            return self._records

        # Initialize our data structure
        data = {}

        # Iterate over the records and build the dictionary
        for record in self._records:
            # The record Id is the first three characters.  The first two
            # are the command that was requested and the third is the record
            # number.
            # pylint: disable=consider-using-f-string
            record_id = '%c%c%i' % (record[0], record[1], record[2])
            # pylint: enable=consider-using-f-string

            if record_id == 'ww0':
                data['total_gallons_treated'] = int.from_bytes(record[6:8], byteorder='big')
                data['total_gallons_treated_since_reset'] = int.from_bytes(record[9:11], byteorder='big')
                data['total_regenerations'] = int.from_bytes(record[11:13], byteorder='big')
                data['total_regenerations_since_reset'] = int.from_bytes(record[13:15], byteorder='big')

            elif record_id == 'ww1':
                if include_history is True:
                    # We need to multiple the values by 10 to get the final
                    for index in range(4, len(record)-1):
                        record[index] = int(record[index]) * 10

                    # Extract the list of gallons per day
                    water_usage_gallons_per_day = list(record[3:len(record)-1])
                    water_usage_gallons_per_day.reverse()
                    data['water_usage_gallons_per_day'] = water_usage_gallons_per_day

            elif record_id == 'ww2':
                if include_history is True:
                    # Extract the list of gallons between regenerations
                    gallons_between_regenerations = list(record[3:len(record)-1])
                    gallons_between_regenerations.reverse()
                    data['total_water_usage_gallons_between_regenerations'] = gallons_between_regenerations

            elif record_id == 'ww3':
                if include_history is True:
                    # We need to divide the values by 10 to get the actual values
                    for index in range(3, len(record)-1):
                        record[index] = int(record[index]) / 10

                    # Extract the list of peak flows per day
                    peak_flow_per_day = list(record[3:len(record)-1])
                    peak_flow_per_day.reverse()
                    data['peak_flow_recorded_per_day'] = peak_flow_per_day

        # Return the data
        return data


    def get_all(self, include_history=False, raw=False):
        '''
        Get all data from the Chandler Systems, Inc. Smart Valve

        Arguments:
            include_history=[True|False]
                Specify whether or not to include the histtorical data or just
                the current data.
                (default: False)

            raw=[True|False]
                Specify whether or not to return the raw data received from
                the device or parse the data and return a dictionary.
                (default: False)

        Returns:
            raw=False   A dictionary with named values
            raw=True    A list of raw bytearray records
        '''
        # Initialize our dictionary
        data = {}

        # Get the Dashboard data
        data.update(self.get_dashboard(include_history=include_history, raw=raw))

        # Get the Advanced Settings data
        data.update(self.get_settings())

        # Get the Status / History data
        data.update(self.get_history(include_history=include_history, raw=raw))

        # Return the data
        return data
