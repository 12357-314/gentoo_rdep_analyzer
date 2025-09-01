# Portage Complaints

Portage is great. It would be better if it was clear how to learn the
underlying functions though. 

For example:

```
python

>>> import portage
>>> help(portage.dep.dep_check.dep_check)

Help on function dep_check in module portage.dep.dep_check:

dep_check(
    depstring,
    mydbapi,
    mysettings,
    use='yes',
    mode=None,
    myuse=None,
    use_cache=1,
    use_binaries=0,
    myroot=None,
    trees=None
)
    Takes a depend string, parses it, and selects atoms.
    The myroot parameter is unused (use mysettings['EROOT'] instead). 

```

Of course, this function selects atoms and does not parse a dependency string
(a function that does simply parse dependency strings could not be found in
time), so it does not help here, but it is a good example. While the
`depstring` parameter can be provided easily, the it is unclear what should be
provided as the `mysettings` and `mydbapi` parameters. As far as I know, the
only documentation for finding this information can only be obatined by reverse
engineering the existing source code. The portage module source documentation
can be found [online](https://dev.gentoo.org/~zmedico/portage/doc/api/). There
is [one project](https://gitlab.com/apinsard/appi) that attempts to address the
limitations with portage documentation, but it appears to be abandoned. This
could be an intentional decision from the developers to provide a knowledge
threshold for new contributors so that new contributors cannot shift the
project in another direction or provide low quality commits, but it is more
likely due to resource constraints. Writing documentation takes significant
time and effort that maybe could not be justified for something that is
primarily used only as an internal tool. This would be sort of ironic though
because one can imgaine that good documentation could attract more developers
that would assist the current team.

# Development Environment

To add features to the code, create a fork of the repository or request access
to the main repository. If access to the main repository is present, then
branches can be pushed directly from local repositories. Alternatively, pull
requests can be submitted via email patches. 

A fork of the repository is the recommended way to add features. A fork can be
created under a GitHub account through the GitHub webui. Then a pull request
can be sent using the fork. It is not possible to submit a pull request to
GitHub using git alone because GitHub pull requests are not something that git
can do by itself. Git only sends an email to the owner of the repository and
requests for code to be pulled from another repository, which is not really the
same thing. 

After creating a fork, the fork repository can be cloned with `git clone`. 

```
git clone URL
cd gentoo_rdep_analyzer
```

Source files are under `gentoo_rdep_analyzer/src/gentoo_rdep_analyzer/`. Test
files are under `gentoo_rdep_analyzer/tests/`.

A virtual environment can be made with `python -m venv venv` if tests need to
be run. 

```
python -m venv venv
python -m pytest
```

It is recommended to create a branch for the new feature being added. 

```
git checkout category/branch-name
```

Where category is an optional category for the branch (feature, bugfix, docs,
etc.) and branch-name is a action describing what the branch will add to the
code when applied (update-readme, fix-parser, refactor-use-analyzer).

After changes to the files are made, add all the changes to the staging area
with `git stage`. 

```
git stage .
```

After the changes are staged, they can be coimmitted with the `git commit`
command. 

```
git commit
```

An editor will appear for typing the commit message. This should be a short,
one-line message which states what the commit does to the code. Messages can be
things like "Remove extra content from README.md" or "Split README content into
different files." For very involved or complex commits, a second paragraph can
be added two lines below the first summary line explaining important
information related to the commit. 

Once this is done, the commit can be pushed to the forked repository. 

```
git push origin category/branch-name
```

Then a pull request can be submitted to the upstream repository via GitHub's
webui. It is important that the right branch be selected in the webui for the
fork repository before initiating the pull request so the right branch is
submitted for the pull request. 
