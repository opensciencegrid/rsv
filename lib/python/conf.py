#!/usr/bin/env python

# Standard libraries
import os
import re
import sys
import utils
import ConfigParser
from pwd import getpwnam

# RSV libraries
import rsv

import pdb

def set_defaults():
    """ This is where to declare defaults for config knobs.
    Any defaults should have a comment explaining them.
    """
    
    rsv.CONFIG.add_section("rsv")
    rsv.CONFIG.add_section(rsv.OPTIONS.metric)

    def set_default_value(section, key, val):
        """ Set an individual item """
        rsv.CONFIG.set(section, key, val)
        rsv.log("Setting default '%s=%s'" % (key, val), 3, 4)


    # We want remote jobs to execute on the CE headnode, so they need to use
    # the fork jobmanager.
    set_default_value(rsv.OPTIONS.metric, "jobmanager", "fork")

    # The only metricType that any current metric has is "status".  So instead
    # of declaring it in every single <metric>.conf file, we'll set it here but
    # still make it possible to configure in case it is needed in the future.
    set_default_value(rsv.OPTIONS.metric, "metric-type", "status")

    # Just in case the details data returned is enormous, we'll set the default
    # to trim it down to in bytes.  A value of 0 means no trimming.
    set_default_value("rsv", "details-data-trim-length", 10000)

    # Set the job timeout default in seconds
    set_default_value("rsv", "job_timeout", 300)

    return



def load_config():
    """ Load all configuration files:
    Load RSV configuration
    Load metric global configuration
    Load host-specific metric configuration
    """

    # Make the config parser case sensitive
    rsv.CONFIG.optionxform = str

    # Load the default values
    rsv.log("Loading default configuration settings:", 3, 0)
    set_defaults()

    rsv.log("Reading configuration files:", 2, 0)

    conf_files = []

    # The global RSV configuration file
    conf_files.append([os.path.join(rsv.RSV_LOC, "etc", "rsv.conf"), 1])
    # The metric-specific config file
    conf_files.append([os.path.join(rsv.RSV_LOC, "etc", "metrics", rsv.OPTIONS.metric + ".conf"), 1])
    # The host specific config file
    conf_files.append([os.path.join(rsv.RSV_LOC, "etc", "metrics", rsv.OPTIONS.uri, rsv.OPTIONS.metric + ".conf"), 0])

    for tuple in conf_files:
        load_config_file(tuple[0], required=tuple[1])

    #
    # Validate the configuration file
    #
    validate()

    return



def load_config_file(config_file, required):
    """ Parse a configuration file in INI form. """
    
    rsv.log("reading configuration file " + config_file, 2, 4)

    if not os.path.exists(config_file):
        if required:
            rsv.log("ERROR: missing required configuration file '%s'" % config_file, 1)
            sys.exit(1)
        else:
            rsv.log("configuration file does not exist " + config_file, 2, 4)
            return

    # todo - add some error catching here
    rsv.CONFIG.read(config_file)

    return




def validate():
    """ Perform validation on config values """

    #
    # make sure that the user is valid, and we are either that user or root
    #
    rsv.log("Validating user:", 2)
    try:
        user = rsv.CONFIG.get("rsv", "user")
    except ConfigParser.NoOptionError:
        rsv.log("ERROR: 'user' is missing in rsv.conf.  Set this value to your RSV user", 1, 4)
        sys.exit(1)

    try:
        (desired_uid, desired_gid) = getpwnam(user)[2:4]
    except KeyError:
        rsv.log("ERROR: The '%s' user defined in rsv.conf does not exist" % user, 1, 4)
        sys.exit(1)

    # If appropriate, switch UID/GID
    utils.switch_user(user, desired_uid, desired_gid)

                
    #
    # "details_data_trim_length" must be an integer because we will use it later
    # in a splice
    #
    try:
        rsv.CONFIG.getint("rsv", "details_data_trim_length")
    except ConfigParser.NoOptionError:
        # We set a default for this, but just to be safe...
        rsv.CONFIG.set("rsv", "details_data_trim_length", "10000")
    except ValueError:
        rsv.log("ERROR: details_data_trim_length must be an integer.  It is set to '%s'"
                % rsv.CONFIG.get("rsv", "details_data_trim_length"), 1)
        sys.exit(1)


    #
    # job_timeout must be an integer because we will use it later in an alarm call
    #
    try:
        rsv.CONFIG.getint("rsv", "job_timeout")
    except ConfigParser.NoOptionError:
        # We set a default for this, but just to be safe...
        rsv.CONFIG.set("rsv", "job_timeout", "300")
    except ValueError:
        rsv.log("ERROR: job_timeout must be an integer.  It is set to '%s'" %
                rsv.CONFIG.get(rsv.OPTIONS.metric, "job_timeout"), 1)
        sys.exit(1)


    #
    # warn if consumers are missing
    #
    try:
        consumers = rsv.CONFIG.get("rsv", "consumers")
        rsv.log("Registered consumers: %s" % consumers, 2, 0)
    except ConfigParser.NoOptionError:
        rsv.CONFIG.set("rsv", "consumers", "")
        rsv.log("WARNING: no consumers are registered in rsv.conf.  This means that\n" +
                "records will not be sent to a central collector for availability\n" +
                "statistics.", 1)


    #
    # check vital configuration for the job
    #
    try:
        rsv.CONFIG.get(rsv.OPTIONS.metric, "service-type")
        rsv.CONFIG.get(rsv.OPTIONS.metric, "execute")
    except ConfigParser.NoOptionError:
        rsv.log("ERROR: metric configuration is missing 'service-type' or 'execute' declaration.\n" +
                "This is likely caused by a missing or corrupt metric configuration file", 1, 0)
        sys.exit(1)


    # 
    # Check the desired output format
    #
    try:
        output_format = rsv.CONFIG.get(rsv.OPTIONS.metric, "output-format").lower()
        if output_format != "wlcg" and output_format != "brief":
            rsv.log("ERROR: output-format can only be set to 'wlcg' or 'brief' (val: %s)\n" %
                    output_format, 1, 0)
            sys.exit(1)
                    
    except ConfigParser.NoOptionError:
        rsv.log("ERROR: desired output-format is missing.\n" +
                "This is likely caused by a missing or corrupt metric configuration file", 1, 0)
        sys.exit(1)

    #
    # Handle environment section
    #
    try:
        section = rsv.OPTIONS.metric + " env"
        for var in rsv.CONFIG.options(section):
            setting = rsv.CONFIG.get(section, var)
            if setting.find("|") == -1:
                rsv.log("ERROR: invalid environment config setting in section '%s'" +
                        "Invalid entry: %s = %s\n" +
                        "Format must be VAR = ACTION | VALUE\n" % (section, var, setting), 1, 0)
                sys.exit(1)
                
            else:
                (action, value) = re.split("\s*\|\s*", setting, 1)
                valid_actions = ["SET", "UNSET", "APPEND", "PREPEND"]
                if action.upper() in ("SET", "UNSET", "APPEND", "PREPEND"):
                    # todo - This might not be necessary - we should replace it during configuration
                    value = re.sub("!!VDT_LOCATION!!", rsv.OPTIONS.vdt_location, value)
                    rsv.CONFIG.set(section, var, [action, value])
                else:
                    rsv.log("ERROR: invalid environment config setting in section '%s'" +
                            "Invalid entry: %s = %s\n" +
                            "Format must be VAR = ACTION | VALUE\n" +
                            "ACTION must be one of: %s" %
                            (section, var, setting, " ".join(valid_actions)), 1, 0)

    except ConfigParser.NoSectionError:
        rsv.log("No environment section in metric configuration", 2, 4)
    
    return