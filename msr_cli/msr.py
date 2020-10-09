"""
CLI that performs various measurements on remote web pages.
"""
import click
import os
import re
import requests
import sys
import time
import tldextract


from cachecontrol import CacheControl
from collections import defaultdict
from tabulate import tabulate
from threading import Thread
from urllib.parse import urlparse
from validator_collection import checkers
from xdg import XDG_DATA_HOME

FILE_NAME = "msr_registry.txt"
VERSION = "1.0.0"
FILE_DIR = ".local/share/msr/"
FILE_PATH = FILE_DIR + FILE_NAME


@click.group()
def cli():
    pass


@cli.command()
def version():
    """Prints a semver string to STDOUT.
    """
    print(VERSION, file=sys.stdout)


@cli.command()
@click.argument("url")
def register(url):
    """Registers a URL. Validates input URL, and returns with a non-zero exit
    code if the URL is invalid. If the URL is valid, adds the URL to a internal,
    persistent registry.
    """
    # Check if URL is valid using regex
    if not checkers.is_url(url):
        print("Error: invalid URL.")
        return sys.exit(os.EX_DATAERR)

    home = os.path.expanduser("~")
    file_path = os.path.join(home, FILE_PATH)

    if not os.path.exists(FILE_DIR):
        try:
            os.makedirs(os.path.dirname(FILE_DIR))
        except OSError as exc:  # Guard against race condition
            if exc.errno != errno.EEXIST:
                raise

    open(file_path, "a").close()

    with open(file_path, "r+") as file:
        for line in file:
            if url in line:
                file.close()
                return sys.exit(os.EX_OK)
        # Write a space delimited row of the form "url content_num_bytes,
        # load_time_seconds, refresh_time.
        file.write(" ".join([url, "0", "0", "0"]) + "\n")
    file.close()
    return sys.exit(os.EX_OK)


@cli.command()
def measure():
    """Returns a pretty-printed table of all of the URLs in the registry, along
    with the size (in bytes) of the body received by making a GET request to
    that URL. Follows redirects as necessary to get an actual content body.
    """
    try:
        url_to_bytes = []
        update_registry_cache()

        home = os.path.expanduser("~")
        file_path = os.path.join(home, FILE_PATH)
        with open(file_path) as file:
            lines = file.readlines()
            for line in lines:
                data = line.split()
                if not data:
                    continue
                url_to_bytes.append([line.split()[0], line.split()[1]])
    except FileNotFoundError as e:
        print("Warning: No URLs in the registry.")

    print(tabulate(url_to_bytes, tablefmt="plain"), file=sys.stdout)


@cli.command()
def race():
    """Returns a pretty-printed table of all the domains found in the URLs in
    the registry, along with the average page load time for the URLs of that
    domain.
    """
    # Dictionary where the keys are domains and the values are tuples
    # corresponding to the total page load time across all URLs and number of
    # URLs in the domain.
    domain_load_time = defaultdict(lambda: (0.0, 0.0))

    threads = []
    try:
        update_registry_cache()

        home = os.path.expanduser("~")
        file_path = os.path.join(home, FILE_PATH)
        with open(file_path) as file:
            lines = file.readlines()
            for line in lines:
                data = line.split()
                if not data:
                    continue
                url = data[0]
                load_time = float(data[2])
                domain = tldextract.extract(url).domain
                domain_load_time[domain] = (
                    domain_load_time[domain][0] + load_time,
                    domain_load_time[domain][1] + 1,
                )
    except FileNotFoundError as e:
        print("Warning: No URLs in the registry.")

    domain_to_avg_load_time = []
    for key, value in domain_load_time.items():
        domain_to_avg_load_time.append([key, value[0] / value[1]])

    print(tabulate(domain_to_avg_load_time, tablefmt="plain"), file=sys.stdout)


def update_registry_cache():
    """Updates the cached load time and content bytes values in the registry
    cache. Only updates outdated pages as per the cache-control specifications.
    """

    home = os.path.expanduser("~")
    file_path = os.path.join(home, FILE_PATH)
    with open(file_path, "r+") as file:
        lines = file.readlines()
        threads = []

        for i in range(len(lines)):
            process = Thread(target=update_line, args=[lines, i])
            process.start()
            threads.append(process)

        for thread in threads:
            thread.join()

        file.seek(0)
        file.truncate(0)
        file.writelines(lines)


def update_line(lines, i):
    data = lines[i].split()

    if float(data[3]) < time.time():
        response = requests.get(data[0])
        data[1] = str(len(response.content))
        data[2] = str(response.elapsed.total_seconds())
        try:
            cache_control = response.headers["cache-control"]
            max_age = cache_control.split("max-age=")[1].split(",")[0]
            data[3] = str(time.time() + float(max_age))
        except:
            pass
    lines[i] = " ".join(data) + "\n"
