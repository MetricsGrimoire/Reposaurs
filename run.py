REPOSITORIES_FILES = {
                       'cvsanaly' : ("cvsanaly_repos.conf", "cvsanaly_repos_blacklist.conf"),
                       'gerrit'   : ("gerrit_trackers.conf", "gerrit_trackers_blacklist.conf"),
                     }



def remove_repositories(repositories, db_user, db_pass, database, tool):
    if tool == 'gerrit':
        tool = 'bicho'

    for r in repositories:
        main_log.info("Removing %s " % (r))
        # Remove not found projects.
        # WARNING: if a repository name is different from the one in the database
        # list of repositories, this piece of code may remove all
        # of the repositories in the database.
        # An example would be how Gerrit returns the name of the projects, while
        # Bicho stores such information in URL format.
        proc = subprocess.Popen([tools['rremoval'], "-u", db_user, "-p", db_pass,
                                "-d", database, "-b", tool, "-r", r],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output = proc.communicate()


def encode_repositories(tool, source, repositories):
    if tool == 'bicho' or tool == 'gerrit':
        return [source + '_' + repo for repo in repositories]
    else:
        return repositories


def read_repository_file(filepath):
    with open(filepath, 'r') as fd:
        repositories = fd.readlines()
    return repositories


def read_repositories_files(tool):
    global conf_dir

    if tool not in REPOSITORIES_FILES:
        main_log.info("[SKIPPED] Repositories files not available for %s" % tool)
        return [], []

    files = REPOSITORIES_FILES[tool]

    # Read repositories list
    filepath = os.path.join(conf_dir, files[0])
    repos = read_repository_file(filepath)

    # Read blacklisted repositories list
    filepath = os.path.join(conf_dir, files[1])
    blacklisted = read_repository_file(filepath)

    return repos, blacklisted


def get_current_repositories(db_user, db_pass, database, tool):
    if options[tool].has_key('projects'):
        repositories = [r.replace('"', '') for r in options[tool]['projects']]
    else:
        if tool == 'gerrit':
            tool = 'bicho'

        p = subprocess.Popen([tools['rremoval'], "-u", db_user, "-p", db_pass,
                             "-d", database, "-b", tool, "-l"],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output = p.communicate()
        repositories = eval(output[0])

    return repositories


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
    # db_user, db_pass, mode, database, source, whitelist file, blacklist file
    # read files  (remember, different formats)
    # get current repos from db [and scm/]
    # remove repos (blacklist)
    # calculate whitlelist
    # clone W or add W to a file
    # if mode == hard: delete repos from DB not in whitelist
    # if mode == soft: notify repos from DB not in whitelist
