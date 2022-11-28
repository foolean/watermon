# watermon

Water softener monitor

## Dependencies

    * python3
        * argparse
        * configparser
        * datetime
        * logging
        * signal
        * sys
        * threading
        * time
    * psycopg2
    * pygatt


## Usage

    usage: wmpoller [-h] -a MAC [-c CALIBRATION] [-d] [-o]

    Poll/monitor a Chandler Systems, Inc. Smart Valve

    options:
    -h, --help            show this help message and exit
    -a MAC, --address MAC
                          Bluetooth Low-Energy (BLE) MAC address of the meter
    -c CALIBRATION, --calibration CALIBRATION
                          Calibration value used when calculating usage based on flow rate [default: 1]
    -C CONFIG, --config CONFIG
                          Specify an alternate configuration file [default: None]
    -d, --debug           Print debugging messages
    -o, --onetime         Run one time and exit

### configuration

    The default configuration file name is 'wmpoller.conf'

    wmpoller looks for the configuration file in the following locations:
        * /etc/wmpoller.conf
        * /usr/local/etc/wmpoller.conf

### calibration

    We attempt to determine the gallons used based on flow rates
    read every second.  The reality is that we don't read on every
    and thus are sometimes off.  It would be more accurate to read
    the flow rate several times per second but the meter is not able
    to handle it.  The calibration factor is an attempt to compensate
    for this inconsistency so that longer term monitoring eventually
    normalizes to a more accurate value.


## Linting

    pylint --rcfile=pylintrc <file_to_be_linted>


## License

    Watermon - Water softener monitor
    Copyright (C) 2021 Bennett Samowich

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.

