# Introduction

Gentoo Atom Reverse Dependency Tree Analyzer

The goal of this program is to show the reasons a given atom is installed. This
is done by calculating and outputting to `stdout` the full reverse dependency
tree of the given atom. The reverse dependency tree output shows each dependee
and the `USE` flags that trigger the installation of each one up the reverse
dependency tree until the explicitly installed "root" atoms in the `@selected`
group listed in the `world` file at `/var/lib/portage/world` or other group
such as the `@system` group are reached.

# Attempted Solutions

The goal at first seems to be achieved by `equery d -D <ATOM>`, which outputs
the reverse dependency tree for a given atom. There are two immediate issues
with the output of this command. It does not differentiate between enabled and
disabled use flags and it seems to skip some use flags.

For example, when attempting to determine why the `bluez` atom is installed,
one might run `equery d --depth=1 net-wireless/bluez`. Listed in the output
could be `sys-kernel/gentoo-kernel-6.12.28 (net-wireless/bluez)`. This would
normally be interpreted  as saying `net-wireless/bluez` is a hard dependency of
`sys-kernel/gentoo-kernel`, but this is actually not the case.
`net-wireless/bluez` is listed as a dependency for `sys-kernel/gentoo-kernel`
under the dynamic use flag `generic-uki?`, which is masked and disabled by
default as shown by `emerge --info sys-kernel/gentoo-kernel` and `equery use -f
sys-kernel/gentoo-kernel`. Installing `sys-kernel/gentoo-kernel` did not result
in the `bluez` atom being installed. 

This program's purpose is to show, using the use flags enabled on a given
Gentoo system, the use flags whose being enabled results in the target atom 
being installed. If the use flag wasn't toggled in the right way, then it
doesn't result in the atom being installed and the atom should not be listed in
the output.

While there is an official portage python module which has some [source
documentation](https://dev.gentoo.org/~zmedico/portage/doc/api/), there appears
to be [almost zero usage
documentation](https://forums.gentoo.org/viewtopic-t-1168219-highlight-portage+python+api.html)
which makes it very difficult to know how these components are meant to
interact with each other.

The solution used with this project is to parse the required information from a
few command line utilities and extracting the desired information. This
undoubtedly duplicates work, but writing documentation for the portage python
module is a future project that is not best accomplished by someone unfamiliar
with the codebase. 

# Downloading

The program can be downloaded with `git`.

```
git clone https://github.com/12357-314/gentoo_rdep_analyzer.git
```

# Installing

No install mechanism currently exists. 

# Running

Run the `gentoo_rdep_analyzer` module located inside the cloned git repository. 

```
python -m gentoo_rdep_analyer.src.gentoo_rdep_analyzer ~/emerge_rdeps.txt
```

But first, the `emerge_rdeps.py` file must be created. 

```
emerge --pretend --verbose --emptytree --depclean > ~/emerge_rdeps.txt
```

Or a virtual environment can be created to install the package to. 

```
cd gentoo_rdep_analyzer
python -m venv venv
pip install -e .
emerge --pretend --verbose --emptytree --depclean > ./emerge_rdeps.txt
python -m gentoo_rdep_analyzer ./emerge_rdeps.txt
```

If the `emerge_rdeps` file is not provided, the script will run the command in
the background each time it is run. This can take some time, so caching the
output in a file can be quicker. 

# Documentation

There is no significant documentation beyond the README file at this time other
than snippets in the `docs` folder. 

Open an issue or send an email to request any additional details about the
program. Contact information is at the end of the `README.md` file. 

# Testing

`pytest` is used to run tests. It can be installed as follows.

```
# Change directories into the cloned revdep git repository.
cd gentoo_rdep_analyzer

python -m venv venv
source ./venv/bin/activate
pip install pytest

# `pytest` alone won't work: 
python -m pytest
```

> NOTE: Only the parser and a few other parts of the code have tests written
> for them. 

# Program Overview

The program works by parsing the output from the following emerge command to
get the dependees of all installed atoms. The output is provided via a
filename as the first argument to the program. 

```
emerge --pretend --verbose --emptytree --depclean
```

Then it uses this list of atoms to prompt the user for one atom to analyze.
Once an atom is given, the program will check the `USE` flags for each
dependency in the list. For each of the dependees in the reverse dependency
tree the use flags are scraped from the following

```
portageq metadata / ebuild $(qlist -Iv <PKG>) \
    DEPEND RDEPEND BDEPEND IDEPEND PDEPEND
```

The program creates a syntax tree from the following parsed dependency
variables if they are defined: DEPEND, BDEPEND, RDEPEND, PDEPEND, IDEPEND. The
program works through these syntax trees to determine the use flags that pulled
in the last dependency. It does this repeatedly until the ends of the tree are
found and then outputs the results in an indented tree-like format. 

The parser uses the package manager specifications
((PMS)[https://dev.gentoo.org/~ulm/pms/head/pms.pdf]) from Gentoo. 

# Advantages

There are no dependencies required to run the program. Pytest is only needed to
run tests. 

# Limitations

The program is somewhat slow. This might just be a reality of using python and
parsing the dependency requirements of so many atoms, but I also know the
parser isn't as efficient as it could be.

The program also does not actually verify if the `USE` flags it is listing as
the trigger for a atom to be installed are actually enable on the system,
meaning if there are multiple `USE` flags that could trigger the installation
of an atom, but only one is enabled, then the program may output multiple `USE`
flags as triggering the installation of a package when only one is actually
enabled. The packages included in the `emerge_rdeps.txt` file should only be
included if at least one of these use flags was actually enabled. 

Tests are not written for the entire program. Coverage is mostly limited to the
tree and parser classes. 

The program does not have an EBUILD

The program is new. There are likely unknown issues that will appear during
regular use. 

# Questions

I am interested in discussing topics that could potentially help to find a
better way to accomplish the goals of this program. Please open an issue or
contact me to discuss.

# Contact

Email: `gentoo_rdep_analyzer [at] delta0189 [dot] xyz`

Or open an issue. 

# TODO Status

- Add an ebuild for packaging with Gentoo: No solution being developed. 
- Add tests for the remaining functions in the project: Solution progressing. 
- Consider splitting the large source file into multiple modules: No solution being developed. 
- Consider splitting the large test file into multiple modules: No solution being developed. 
- Add check to ensure detected USE flags are also enabled on the system: No solution being developed. 
