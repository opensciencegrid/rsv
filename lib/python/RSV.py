#!/usr/bin/env python

""" Shared code between rsv-control and run-rsv-metric """

# System libraries
import os
import re
import sys
import logging
import ConfigParser

# RSV libraries
import Host
import Metric

import pdb


class RSV:
    vdt_location = None
    rsv_location = None
    config = None
    logger = None
    quiet = 0

    def __init__(self, vdt_location=None, verbosity=1):

        # Setup rsv_location
        if vdt_location:
            self.vdt_location = vdt_location
            self.rsv_location = os.path.join(vdt_location, "osg-rsv")
        else:
            self.vdt_location = get_osg_location()
            self.rsv_location = os.path.join(self.vdt_location, "osg-rsv")

        # For any messages that won't go through the logger
        if verbosity == 0:
            self.quiet = 1

        # Setup the logger
        self.init_logging(verbosity)

        # Setup the initial configuration
        self.config = ConfigParser.RawConfigParser()
        self.config.optionxform = str
        self.setup_config()


    def setup_config(self):
        defaults = get_rsv_defaults()
        if defaults:
            for section in defaults.keys():
                if not self.config.has_section(section):
                    self.config.add_section(section)
                    
                for item in defaults[section].keys():
                    self.config.set(section, item, defaults[section][item])

        self.load_config_file(os.path.join(self.rsv_location, "etc", "rsv.conf"), 1)



    def load_config_file(self, config_file, required):
        """ Parse a configuration file in INI form. """
    
        self.log("INFO", "reading configuration file " + config_file, 4)

        if not os.path.exists(config_file):
            if required:
                self.log("ERROR", "missing required configuration file '%s'" % config_file)
                sys.exit(1)
            else:
                self.log("INFO", "configuration file does not exist '%s'" % config_file, 4)
                return

        try:
            self.config.read(config_file)
        except ConfigParser.ParsingError, err:
            self.log("CRITICAL", err)
            sys.exit(1)

        return


    
    def get_installed_metrics(self):
        """ Return a list of installed metrics """
        metrics_dir = os.path.join(self.rsv_location, "bin", "metrics")
        try:
            files = os.listdir(metrics_dir)
            files.sort()
            metrics = []
            for file in files:
                # Somewhat arbitrary pattern, but it won't match '.', '..', or '.svn'
                if re.search("\w\.\w", file):
                    metrics.append(file)
            return metrics
        except OSError:
            # todo - check for permission problem
            self.log("ERROR", "The metrics directory does not exist (%s)" % metrics_dir)
            return []


        
    def get_metric_info(self):
        """ Return a dictionary with information about each installed metric """

        dict = {}
        for metric in self.get_installed_metrics():
            dict[metric] = Metric.Metric(metric, self)

        return dict



    def get_hosts(self):
        """ Return a list of hosts that have configuration files """

        conf_dir = os.path.join(self.rsv_location, "etc")
        try:
            files = os.listdir(conf_dir)
            hosts = []
            for file in files:
                # Somewhat arbitrary pattern, but it won't match '.', '..', or '.svn'
                if re.search("\.conf$", file) and file != "rsv.conf":
                    host = re.sub("\.conf$", "", file)
                    hosts.append(host)
            return hosts
        except OSError:
            # todo - check for permission problem
            self.log("ERROR", "The conf directory does not exist (%s)" % conf_dir)



    def get_host_info(self):
        """ Return a dictionary with host configuration """

        dict = {}
        for host in self.get_hosts():
            dict[host] = Host.Host(host, self)

        return dict



    def init_logging(self, verbosity):

        logger = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter("%(levelname)s: %(message)s")
        logger.setFormatter(formatter)
        if verbosity == 0:
            logger.setLevel(logging.CRITICAL)
        elif verbosity == 1:
            logger.setLevel(logging.WARNING)
        elif verbosity == 2:
            logger.setLevel(logging.INFO)
        elif verbosity == 3:
            logger.setLevel(logging.DEBUG)

        self.logger = logging.getLogger()
        self.logger.addHandler(logger)


    def log(self, level, message, indent=0):

        level = level.lower()

        if indent > 0:
            message = " "*indent + message

        if level == "debug":
            self.logger.debug(message)
        elif level == "info":
            self.logger.info(message)
        elif level == "warning":
            self.logger.warning(message)
        elif level == "error":
            self.logger.error(message)
        elif level == "critical":
            self.logger.critical(message)
        else:
            self.logger.warning("Invalid level (%s) passed to RSV.log." % level)
            selg.logger.warning(message)

    def echo(self, message, indent=0):

        if self.quiet:
            return
        else:
            if indent > 0:
                message = " "*indent + message

            print message
        


    def get_metric_log_dir(self):
        return os.path.join(self.rsv_location, "logs", "metrics")

    def get_consumer_log_dir(self):
        return os.path.join(self.rsv_location, "logs", "consumers")

    def get_user(self):
        try:
            return self.config.get("rsv", "user")
        except:
            self.log("ERROR", "'user' not defined in rsv.conf")
            return ""


    def get_enabled_consumers(self):

        
        try:
            consumers = []
            for consumer in re.split("\s*,\s*", self.config.get("rsv", "consumers")):
                if not consumer.isspace():
                    consumers.append(consumer)
            return consumers
        except ConfigParser.NoOptionError:
            self.log("WARNING", "No consumers defined in rsv.conf")
            return []


    def get_wrapper(self):
        return os.path.join(self.rsv_location, "bin", "run-rsv-metric")


# End of RSV class


def get_osg_location():
    """ Find the path to OSG root directory """
    return os.environ.get("OSG_LOCATION", os.environ.get("VDT_LOCATION", ""))


def get_rsv_defaults():
    """
    This is where to declare defaults for config knobs.
    Any defaults should have a comment explaining them.
    """

    defaults = {}

    def set_default_value(section, option, value):
        if section not in defaults:
            defaults[section] = {}
        defaults[section][option] = value

    # Just in case the details data returned is enormous, we'll set the default
    # to trim it down to in bytes.  A value of 0 means no trimming.
    set_default_value("rsv", "details-data-trim-length", 10000)

    # Set the job timeout default in seconds
    set_default_value("rsv", "job-timeout", 300)

    return defaults
