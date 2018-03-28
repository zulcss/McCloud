#!/usr/bin/env python
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

import argparse
import json
import os
import os.path
import re
import sys
import time
import yaml


# Deployment Scenario Count keys
nr_count = [
    "ControllerCount",
    "NetworkerCount",
    "CephStorageCount",
    "ObjectStorageCount",
    "BlockStorageCount",
]
# Matching pin for each Deployment Scenario Count Key
nr_pin = [
    "controller-",
    "networker-",
    "cephstorage-",
    "objectstorage-",
    "blockstorage-",
]

def create_homogeneous_yamls(servers, d_scenarios, scenario, pin_dir, dy_dir):
    server_idx = 0
    ds = d_scenarios["scenarios"][scenario]
    with open(os.path.join(pin_dir, "deploy{}-pin.yaml".format(scenario)), "w") as pin_yaml, \
            open(os.path.join(dy_dir, "deploy{}.yaml".format(scenario)), "w") as deploy_yaml:
        pin_yaml.write("# Generated by node-assignment.py\n")
        pin_yaml.write("# Scenario: {}\n".format(scenario))
        deploy_yaml.write("# Generated by node-assignment.py\n")
        deploy_yaml.write("# Scenario: {}\n".format(scenario))
        deploy_yaml.write("parameter_defaults:\n")
        for n_role, npin in zip(nr_count, nr_pin):
            if n_role in ds:
                deploy_yaml.write("  {}: {}\n".format(n_role, ds[n_role]))
                for idx in range(0, ds[n_role]):
                    pin_yaml.write("{}: {}{}\n".format(servers[server_idx]["node_pin"], npin, idx))
                    server_idx += 1
            else:
                deploy_yaml.write("  {}: 0\n".format(n_role))
        # Computes
        if "ComputeHCI" in ds and ds["ComputeHCI"] == True:
            npin = "computehci-"
            n_role = "ComputeHCI"
        else:
            npin = "compute-"
            n_role = "Compute"
        deploy_yaml.write("  {}: {}\n".format(n_role, len(servers) - server_idx))
        # Extra deploy yaml data
        for idx, server in enumerate(range(server_idx, len(servers))):
            pin_yaml.write("{}: {}{}\n".format(servers[server_idx]["node_pin"], npin, idx))
            server_idx += 1
        if "deploy_yaml_extra" in d_scenarios["scenarios"][scenario]:
            for line in d_scenarios["scenarios"][scenario]["deploy_yaml_extra"]:
                deploy_yaml.write("{}\n".format(line))


def remove_undercloud(instackenv_json, uc_pm_addr):
    nodes = []
    with open(instackenv_json, "r") as rf:
        instackenv = json.load(rf)
        for node in instackenv["nodes"]:
            if uc_pm_addr in node["pm_addr"][0:node["pm_addr"].find(".")]:
                print "WARN :: Found Undercloud included in the instackenv"
                continue
            nodes.append(node)
    with open(instackenv_json, "w") as wf:
        data = {
            "nodes": nodes,
        }
        json.dump(data, wf, indent=4, sort_keys=True)


def main():
    script_dir = os.path.dirname(os.path.realpath(__file__))
    parser = argparse.ArgumentParser(
        description="Reads instackenv and generates deployment yamls.", prog="node-assignment.py")
    parser.add_argument(
        "-i", "--instackenv", default="instackenv.json", help="Pass instackenv.json file.")
    parser.add_argument(
        "-r", "--pm-addr-regex", default="^perf-([a-z0-9]+)-[0-9]-[0-9]-mm$",
        help="Regex to get Node Type on pm_addr.  Defaults to '^perf-([a-z0-9]+)-[0-9]-[0-9]-mm$'")
    parser.add_argument(
        "-s", "--scenarios-file", default="deploy-scenarios.yaml",
        help="Deploy scenarios yaml file.  Defaults to 'deploy-scenarios.yaml'")
    parser.add_argument(
        "-p", "--pin-output-directory", default="pin-definitions",
        help="Directory for pin-definitions. Defaults to 'pin-definitions'")
    parser.add_argument(
        "-y", "--deploy-yaml-output-directory", default="templates",
        help="Directory for deploy yamls. Defaults to 'templates'")
    parser.add_argument(
        "-u", "--undercloud-ipmi-addr", default=None,
        help="Undercloud pm_addr to remove mistakenly included underclouds in instackenv.")
    cliargs = parser.parse_args()

    print "INFO :: Node-assignment.py reading in {}".format(cliargs.instackenv)
    print "INFO :: Script directory: {}".format(script_dir)

    if os.path.isfile(cliargs.instackenv):
        instackenv_json = cliargs.instackenv
    else:
        instackenv_json = os.path.join(script_dir, cliargs.instackenv)

    if not os.path.isfile(instackenv_json):
        print "ERROR :: Can not find {}".format(cliargs.instackenv)
        sys.exit(1)

    pin_dir = cliargs.pin_output_directory
    if not os.path.exists(pin_dir):
        os.makedirs(pin_dir)
    if not os.path.isdir(pin_dir):
        print "ERROR :: Pin Output Directory exists as a file: {}".format(pin_dir)
        sys.exit(1)

    dy_dir = cliargs.deploy_yaml_output_directory
    if not os.path.exists(dy_dir):
        os.makedirs(dy_dir)
    if not os.path.isdir(dy_dir):
        print "ERROR :: Deploy Yaml Output Directory exists as a file: {}".format(dy_dir)
        sys.exit(1)

    if os.path.isfile(cliargs.scenarios_file):
        ds_yaml_file = cliargs.scenarios_file
    else:
        ds_yaml_file = os.path.join(script_dir, cliargs.scenarios_file)

    if not os.path.isfile(ds_yaml_file):
        print "ERROR :: Can not find {}".format(cliargs.scenarios_file)
        sys.exit(1)

    print "INFO :: Opening instackenv file: {}".format(instackenv_json)
    print "INFO :: Deploy Scenarios file: {}".format(ds_yaml_file)
    print "INFO :: Writing pin-definitions in {}".format(pin_dir)
    print "INFO :: Creating deploy yamls in {}".format(dy_dir)

   # Remove UC from instackenv (if if is accidently included into the instackenv.json)
    if cliargs.undercloud_ipmi_addr:
        remove_undercloud(instackenv_json, cliargs.undercloud_ipmi_addr)

    # Assemble servers list of node pins/types
    servers = []
    with open(instackenv_json, "r") as of:
        instackenv = json.load(of)
        for node in instackenv["nodes"]:
            node_pin = node["pm_addr"][0:node["pm_addr"].find(".")]
            try:
                node_type = re.search(cliargs.pm_addr_regex, node_pin).group(1)
            except AttributeError:
                node_type = ''
                print "ERROR :: Unable to determine node_type with node({}) using regex '{}'".format(node_pin, cliargs.pm_addr_regex)
                sys.exit(1)
            servers.append({"node_type": node_type, "node_pin": node_pin})

    # Check if Nodes all of same type:
    node_type_set = set()
    for server in servers:
        node_type_set.add(server['node_type'])
    print "INFO :: Node Type(s) Found: {}".format(", ".join(node_type_set))

    if len(node_type_set) == 1:
        # Homogeneous hardware based on node_type regex and pm_addr
        print "INFO :: Homogeneous hardware set"
        with open(ds_yaml_file, "r") as stream:
            d_scenarios = yaml.load(stream)
            for scenario in d_scenarios["scenarios"]:
                create_homogeneous_yamls(servers, d_scenarios, scenario, pin_dir, dy_dir)
    else:
        print "ERROR :: Non-homogeneous instackenv.json not supported with this tooling (yet)."
        sys.exit(1)

if __name__ == "__main__":
    sys.exit(main())