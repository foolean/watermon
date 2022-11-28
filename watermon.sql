/*
 *  watermon.sql
 *      Basic commands to configure the watermon users and tables.
 *
 *  Note: this has only been tested on postgres
 *
 *  Usage:
 *      Change the passwords below and run
 *          psql -U <db_admin_user> -d <db_name> -a -f watermon.sql
 */

/*
 * Create the read and write users
 *
 * NOTE:
 * Be sure to change the password and user to suit your
 * policies and need.  Don't forget to update the grants
 * below if you change the usernames.
 */
CREATE USER watermon_w WITH PASSWORD 'watermon_w';
CREATE USER watermon_r WITH PASSWORD 'watermon_r';

/* Create the table for storing realtime data */
CREATE TABLE watermon_realtime (
    last_update                         TIMESTAMP(3),
    device                              VARCHAR(25) PRIMARY KEY,
    time_of_day_on_unit                 VARCHAR(10),
    battery_on_unit                     NUMERIC,
    current_water_flow                  NUMERIC,
    soft_water_remaining                NUMERIC,
    water_usage_today                   NUMERIC,
    peak_flow_today                     NUMERIC,
    water_hardness                      NUMERIC,
    regeneration_time                   VARCHAR(10),
    average_water_usage_per_day         NUMERIC,
    days_until_regeneration             NUMERIC,
    regeneration_day_override           NUMERIC,
    reserve_capacity                    NUMERIC,
    resin_grains_capacity               NUMERIC,
    backwash                            NUMERIC,
    brine_draw                          NUMERIC,
    rapid_rinse                         NUMERIC,
    brine_refill                        NUMERIC,
    total_gallons_treated               NUMERIC,
    total_gallons_treated_since_reset   NUMERIC,
    total_regenerations                 NUMERIC,
    total_regenerations_since_reset     NUMERIC,
    total_gallons_used                  NUMERIC
);

/* Create the table for storing the timeseries usage data */
CREATE TABLE watermon (
    time_utc            TIMESTAMP(3),
    device              VARCHAR(25),
    total_gallons_used  NUMERIC
);

/* Create an index to help performance */
CREATE INDEX watermon_device ON watermon (time_utc, device);

/*
 * Allow the write user to UPDATE the realtime data.
 *  (this(also requires INSERT and SELECT)
 */
GRANT INSERT, SELECT, UPDATE ON watermon_realtime TO watermon_w;

/* Allow the write user to INSERT only to the timeseries data */
GRANT INSERT ON watermon TO watermon_w;

/* Allow the read user to SELECT only */
GRANT SELECT ON watermon, watermon_realtime to watermon_r;

