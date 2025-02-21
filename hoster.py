#!/usr/bin/python3
import docker
import argparse
import shutil
import signal
import time
import sys
import os

label_name = "hoster.domains"
enclosing_pattern = "#-----------Docker-Hoster-Domains----------\n"
hosts_path = "/tmp/hosts"
containers = {}

def signal_handler(signal, frame):
    global containers
    containers = {}
    update_hosts_file()
    sys.exit(0)

def main():
    # register the exit signals
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    args = parse_args()
    global hosts_path
    hosts_path = args.file

    dockerClient = docker.APIClient(base_url='unix://%s' % args.socket)
    events = dockerClient.events(decode=True)
    #get running containers
    for c in dockerClient.containers(quiet=True, all=False):
        container_id = c["Id"]
        container = get_container_data(dockerClient, container_id)
        containers[container_id] = container

    update_hosts_file()

    #listen for events to keep the hosts file updated
    for e in events:
        if e["Type"]!="container": 
            continue
        
        status = e["status"]
        if status =="start":
            container_id = e["id"]
            container = get_container_data(dockerClient, container_id)
            containers[container_id] = container
            update_hosts_file()

        if status=="stop" or status=="die" or status=="destroy":
            container_id = e["id"]
            if container_id in containers:
                containers.pop(container_id)
                update_hosts_file()

        if status=="rename":
            container_id = e["id"]
            if container_id in containers:
                container = get_container_data(dockerClient, container_id)
                containers[container_id] = container
                update_hosts_file()


def get_container_data(dockerClient, container_id):
    #extract all the info with the docker api
    info = dockerClient.inspect_container(container_id)
    container_hostname = info["Config"]["Hostname"]
    container_ip = info["NetworkSettings"]["IPAddress"]
    if info["Config"]["Domainname"]:
        container_hostname = container_hostname + "." + info["Config"]["Domainname"]
    
    hosts = {}

    if container_ip and container_hostname:
        hosts[container_ip] = set([container_hostname])

    for values in info["NetworkSettings"]["Networks"].values():
        if values["DNSNames"]:
            names = hosts.setdefault(values["IPAddress"], set())
            names.update(values["DNSNames"])
    
    return hosts


def update_hosts_file():
    if len(containers)==0:
        print("Removing all hosts before exit...")
    else:
        print("Updating hosts file with:")

    for id,hosts in containers.items():
        for ip,domain in hosts.items():
            print(f"ip: {ip} domains: {domain}")

    #read all the lines of thge original file
    lines = []
    with open(hosts_path,"r+") as hosts_file:
        lines = hosts_file.readlines()

    #remove all the lines after the known pattern
    for i,line in enumerate(lines):
        if line==enclosing_pattern:
            lines = lines[:i]
            break

    #remove all the trailing newlines on the line list
    while lines:
        if lines[-1].strip() == "":
            lines.pop()
        else:
            break

    #append all the domain lines
    if len(containers)>0:
        lines.append("\n\n"+enclosing_pattern)
        
        for id, hosts in containers.items():
            for ip,domains in hosts.items():
                if os.environ.get("DOCKER_HOSTER_DOMAIN_SUFFIX"):
                    domains = [d + os.environ.get("DOCKER_HOSTER_DOMAIN_SUFFIX") for d in domains]
                lines.append(f"{ip} {" ".join(domains)}\n")

    #write it on the auxiliar file
    aux_file_path = hosts_path+".aux"
    with open(aux_file_path,"w") as aux_hosts:
        aux_hosts.writelines(lines)

    #replace etc/hosts with aux file, making it atomic
    shutil.move(aux_file_path, hosts_path)


def parse_args():
    parser = argparse.ArgumentParser(description='Synchronize running docker container IPs with host /etc/hosts file.')
    parser.add_argument('socket', type=str, nargs="?", default="tmp/docker.sock", help='The docker socket to listen for docker events.')
    parser.add_argument('file', type=str, nargs="?", default="/tmp/hosts", help='The /etc/hosts file to sync the containers with.')
    return parser.parse_args()

if __name__ == '__main__':
    main()

