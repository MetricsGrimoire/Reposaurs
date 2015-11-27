#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright (C) 2015 Bitergia
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.
#
# Authors :
#       Luis Cañas-Díaz <lcanas@bitergia.com>
#
#
# This script automates the checkout of Git repositories based on two lists,
# one with all the repos and the other with a blacklist

import sys
import logging
import subprocess
import os
import MySQLdb
import shutil
import git
from optparse import OptionGroup, OptionParser

TOOLS = {
    'rremoval': '/usr/local/bin/rremoval'
    }

PROGRAM_NAME = "Reposaurs"


# Some ideas for the future:
# - recover mode: if repo is in database and not in scmdir, fetch it

def connect_db():
    try:
        if opts.dbpassword:
            db = MySQLdb.connect(host="localhost", port=3306, user=opts.dbuser,
                                passwd=opts.dbpassword, db=opts.dbname)
        else:
            db = MySQLdb.connect(host="localhost", port=3306, user=opts.dbuser,
                                db=opts.dbname)
        cursor = db.cursor()
        return cursor
    except MySQLdb.Error:
        logger.error("There was a problem in connecting to the database")
        print "\nOups! There was a problem in connecting to the database." +\
        "\nPlease ensure that the database exists on the local host system "+ \
        "and the MySQL service is running.\n"
        raise MySQLdb.Error
    #except MySQLdb.Warning:
    #    pass

def checkout_repositories(repos, opts):
    for r in repos:
        checkout_single_repo(r,opts)

def checkout_single_repo(repo, opts):
    def _get_dir_name(url):
        url = url.replace('https://','')
        url = url.replace('http://','')
        url = url.replace('git@','')
        url = url.replace('/','__')
        url = url.replace(':','__')
        return url

    """def _add_fake_user(url):
        # we add a fake user to avoid get stuck in the Authentication
        # message when url is a private repo or it does not exist
        if url.rfind("https:") == 0:
            url = url.replace("https://","https://fakeuser:fakepass@")
        elif url.rfind("http:") == 0:
            url = url.replace("http://","http://fakeuser:fakepass@")
        return url"""

    # checkout the remote repos to opts.scmdir
    #url = _add_fake_user(repo)
    url = repo
    repo_dir = opts.scmdir + _get_dir_name(repo)
    logger.debug("cloning %s to %s" % (url, repo_dir))

    if os.path.isdir(repo_dir):
        logger.error("destination directory exists: %s" % repo_dir)
    else:
        try:
            os.environ['GIT_ASKPASS'] = '/bin/echo'
            git.Repo.clone_from(url, repo_dir)
        except git.GitCommandError:
            logger.error("error cloning repo %s to %s" % (url, repo_dir))
            #raise

def encode_repositories(tool, source, repositories):
    if tool == 'bicho' or tool == 'gerrit':
        return [source + '_' + repo for repo in repositories]
    else:
        return repositories

def read_repository_file(filepath):
    with open(filepath, 'r') as fd:
        repositories = fd.readlines()
    return repositories

def read_repositories_files(whitelist_url, blacklist_url):
    # return content both for total list and blacklist
    import urllib3

    http = urllib3.PoolManager()

    w = http.request('GET', whitelist_url)
    b = http.request('GET', blacklist_url)
    # format is plain text
    logger.debug("Data read from %s and %s" % (whitelist_url, blacklist_url))
    return w.data.split(), b.data.split()

def _get_db_repos():
    cursor = connect_db()
    cursor.execute("SELECT uri FROM repositories")
    data = []
    db_rep = [ row[0] for row in cursor.fetchall()]
    cursor.close()
    return db_rep

def get_current_repositories(opts):
    #
    dir_rep = _get_scm_repos(opts.scmdir)
    db_rep = _get_db_repos()
    logger.info("%s git clone directories" % len(dir_rep))
    logger.info("%s repositories in the database" % len(db_rep))
    repos_with_clone = set(dir_rep.keys())
    repos_in_db = set(db_rep)
    logger.info("%s repos with git directory cloned not stored in database" % len(repos_with_clone - repos_in_db))
    logger.info("%s repos in database without git clone directory" % len(repos_in_db - repos_with_clone))

    repos = {}
    for r in db_rep:
        if dir_rep.has_key(r):
            repos[r] = dir_rep[r]
        else:
            repos[r] = None
            logger.warning("repository %s does not have an associated git clone" % r)
            if opts.recovery_mode:
                logger.info("recovering clone for repository %s" % r)
                checkout_single_repo(r, opts)
    return repos

def _get_fetch_url(repo_dir):
    # Gets the Fetch URL for a git clone given
    #FIXME use the Git library to get this
    os.chdir(repo_dir)
    os.environ['GIT_ASKPASS'] = '/bin/echo'
    remote = subprocess.Popen(['git','remote','show','origin'],stdout=subprocess.PIPE)
    grep = subprocess.Popen(['grep', 'Fetch'],stdin=remote.stdout, stdout=subprocess.PIPE)
    remote.wait()
    proc = subprocess.Popen(['cut', '-f5', '-d',' '],stdin=grep.stdout,stdout=subprocess.PIPE)
    grep.wait()
    try:
        url = proc.stdout.readline().split()[0]
    except IndexError:
        url = None
        logger.error("could not get Fetch URL from %s" % repo_dir)
    return url

def _get_scm_repos(dir):
    all_repos = {}
    ##sub_repos = {}
    #if (dir == ''):  dir = scm_dir
    if not os.path.isdir(dir): return all_repos

    repos = os.listdir(dir)
    for r in repos:
        #repo_dir_svn = os.path.join(dir,r,".svn")
        repo_dir_git = os.path.join(dir,r,".git")
        if os.path.isdir(repo_dir_git): #or os.path.isdir(repo_dir_svn):
            url = _get_fetch_url(os.path.join(dir,r))
            all_repos[url] = os.path.join(dir,r)
            logger.debug(" %s with origin %s" % (os.path.join(dir,r), url))

        sub_repos = _get_scm_repos(os.path.join(dir,r))
        #for sub_repo in sub_repos:
        all_repos = dict(all_repos.items() + sub_repos.items())
    return all_repos

def read_options():
    # Generic function used by report_tool.py and other tools to analyze the
    # information in databases. This contains a list of command line options

    parser = OptionParser(usage="usage: %prog [options]",
                          version="%prog 0.1",
                          conflict_handler="resolve")
    parser.add_option("-d", "--database",
                      action="store",
                      dest="dbname",
                      help="Database where information is stored")
    parser.add_option("-u","--dbuser",
                      action="store",
                      dest="dbuser",
                      default="root",
                      help="Database user")
    parser.add_option("-p","--dbpassword",
                      action="store",
                      dest="dbpassword",
                      default="",
                      help="Database password")
    parser.add_option("-m", "--mode",
                      type="choice",
                      choices=["soft","hard"],
                      dest="mode",
                      help="soft, hard mode")
    parser.add_option("-w","--whilelist",
                      action="store",
                      dest="whilelist_url",
                      help="URL of whilelist file")
    parser.add_option("-b","--blacklist",
                      action="store",
                      dest="blacklist_url",
                      help="URL of blacklist file")
    parser.add_option("-l","--log_file",
                      action="store",
                      dest="log_file",
                      help="path of log file")
    parser.add_option("-s","--scmdir",
                      action="store",
                      dest="scmdir",
                      help="Path for git clones")
    parser.add_option("-r","--recover",
                      action="store_true",
                      dest="recovery_mode",
                      help="checkout repos if they are missing from scmdir")
    parser.add_option("-g","--debug",
                      action="store_true",
                      dest="debug",
                      help="sets debug mode")

    (opts, args) = parser.parse_args()

    return opts

def remove_repositories(repositories, db_user, db_pass, database, tool, current_repos = None):
    if tool == 'gerrit':
        tool = 'bicho'

    for r in repositories:
        # Remove not found projects.
        # WARNING: if a repository name is different from the one in the database
        # list of repositories, this piece of code may remove all
        # of the repositories in the database.
        # An example would be how Gerrit returns the name of the projects, while
        # Bicho stores such information in URL format.

        proc = subprocess.Popen([TOOLS['rremoval'], "-u", db_user, "-p", db_pass,
                                "-d", database, "-b", tool, "-r", r],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output = proc.communicate()
        logger.info("%s removed from database" % (r))

        if tool == 'cvsanaly':
            target_dir = current_repos[r]
            if target_dir is not None:
                try:
                    shutil.rmtree(target_dir)
                    logger.info("directory %s removed" % target_dir)
                except OSError as exc:
                    if os.path.isdir(target_dir):
                        logger.error("directory %s couldn't be removed" % target_dir)
                    else:
                        logger.info("directory %s already removed by someone else" % target_dir)
            else:
                logger.warning("directory not present for repo %s" % (r))

def set_up_logger(level, filename):
    logger = logging.getLogger(__name__)
    logger.setLevel(level)

    # create a file handler
    handler = logging.FileHandler(filename)
    handler.setLevel(level)

    # create a logging format
    formatter = logging.Formatter("[%(asctime)s] - %(levelname)s - %(message)s", datefmt='%d/%b/%Y:%H:%M:%S')
    handler.setFormatter(formatter)

    # add the handlers to the logger
    logger.addHandler(handler)
    return logger

def update_repositories_list(db_user, db_pass, database, source, tool):
    repos = get_curret_repositories(db_user, db_pass, database, tool)
    whitelisted, blacklisted = read_repositories_files(tool)

    repos = encode_repositories(tool, source, repos)
    whitelisted = encode_repositories(tool, source, whitelisted)
    blacklisted = encode_repositories(tool, source, blacklisted)

    whitelisted = [r for r in whitelisted if r not in blacklisted]

    # Remove blacklisted repositories if they are found in the database
    blacklisted = [r for r in blacklisted if r in repos]

    # Checking if more than a 5% of the total list is going to be removed.
    # If so, a warning message is raised and no project is removed.
    if len(whitelisted) == 0 or float(len(blacklisted))/float(len(whitelisted)) > 0.05:
        main_log.info("WARNING: More than a 5% of the total number of repositories is required to be removed. No action.")
    else:
        remove_repositories(blacklisted, db_user, db_pass, database, tool)

    # Removing those respositories that are found in the database, but not in
    # the list of repositories.
    to_remove = [r for r in repos if r not in whitelisted]
    main_log.info("Removing the following deprecated repositories from the database")
    if len(whitlelisted) == 0 or float(len(to_remove)) / float(len(whitelisted)) >= 0.05:
        main_log.info("WARNING: More than a 5% of the total number of repositories is required to be removed. No action.")
    else:
        remove_repositories(to_remove, db_user, db_pass, database, tool)

if __name__ == '__main__':

    # read options
    opts = read_options()

    if opts.debug:
        level = logging.DEBUG
    else:
        level = logging.INFO
    logger = set_up_logger(level, opts.log_file)
    logger.info("%s starts .." % PROGRAM_NAME)

    # read files  (remember, different formats)
    all_repos, blacklisted = read_repositories_files(opts.whilelist_url,
                                                    opts.blacklist_url)

    whiteset = set(all_repos) - set(blacklisted)
    whitelist = list(whiteset)

    # get current repos from db [and scm/]
    current_repos = get_current_repositories(opts)

    # calculate whitelist
    current_set = set(current_repos.keys())
    #print("\nRepos to be removed from DB")
    to_be_removed = list(current_set - whiteset)

    # are the studied repos in our whitelist?
    logger.info("%s repos to be removed" % (len(to_be_removed)))
    for tb in to_be_removed: logger.debug("%s to be removed" % tb)

    # remove repos (blacklist)
    # are the repos from blacklist stored in our system?
    remove_repositories(to_be_removed, opts.dbuser, opts.dbpassword,
                                        opts.dbname, 'cvsanaly', current_repos)

    # clone W or add W to a file
    to_be_downloaded = list(whiteset - current_set)
    logger.info("%s repos to be downloaded" % (len(to_be_downloaded)))
    checkout_repositories(to_be_downloaded, opts)

    logger.info("Finished")
