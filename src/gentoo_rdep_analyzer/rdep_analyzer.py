#!/usr/bin/env python3

"""
Gentoo Reverse Dependency Analyzer

Map out the reverse dependency chain for a given package, including USE flags
that trigger the package's installation. Uses emerge --pretend --verbose
--emptytree --depclean output to trace dependencies and portageq to extract
dependency variables to parse.

Usage:
    python rdep_analyze.py [emerge_rdeps.txt]

"""

import re
import sys
import functools
import subprocess

class Tree:
    """
    Recursive tree structure with branches, optional root reference, and data
    attribute.

    Provides methods for traversing branches and for printing the tree. 
    """
    def __init__(self, data=None):
        self.data = data
        self._root = None
        self._branches = []
        self.indent_inc = 2

    @property
    def branches(self):
        return self._branches

    def remove_branches(self, indices):
        self._branches = [
            b for i,b in enumerate(self._branches) if not i in indices]

    def add_branch(self, tree):
        """
        Add a child branch and set its root reference.

        """
        tree._root = self
        self._branches.append(tree)

    def __repr__(self, num_indents=0):
        """
        Return string representation of recursive tree and branch data. 

        """
        output = f"{' '*self.indent_inc*num_indents}{self.data}\n"
        for b in self.branches:
            output += b.__repr__(num_indents + 1)
        if num_indents == 0: return output[:-1]
        return output

    def traverse_branches(self, values, key_func):
        """
        Navigate through tree branches using a sequence of values. 

        For each value in the sequence of values, descend one level deeper into
        the tree. If the value is an integer, select from the previously
        matched branches at that index. Otherwise, apply the supplied key_func
        function to the branches to match against the value and descend into
        the tree using the matched branch. Return the list of branches reached
        at the end of the values.

        """
        trees = [self]
        for value in values:
            if isinstance(value, int):
                trees = [trees[value]]
                continue
            if len(trees) == 1:
                tree = trees[0]
            else:
                raise ValueError("Ambiguous path, multiple options")
            branches_by_value = {}
            for branch in tree.branches:
                branch_value = key_func(branch.data)
                branches_by_value.setdefault(branch_value, []).append(branch)
            trees = branches_by_value.get(value, [])
            if not trees:
                return trees
        return trees


class Parcel:
    """
    Represents a parsed syntax token with information about position, text
    value, and token type. 

    """
    def __init__(self, idx_start, idx_end, value, kind):
        self.idx_start = idx_start
        self.idx_end = idx_end
        self.value = value
        self.kind = kind

    def __repr__(self): return (
        f"{self.kind}: {self.value} "
        f"({self.idx_start},{self.idx_end})"
    )


class Parser:
    """
    Parses a depend variable or other syntax from an ebuild into a syntax tree
    according to the syntax rules from Gentoo's Package Manager Specifications.

    A syntax string is taken as an argument for the constructor, then the
    method corresponding to the given syntax string can be called to parse the
    string. The string is parsed into a list of parcels, which can then be put
    back together into a tree if needed. 

    The class uses the "reads" decorator to assign names to tokens parsed by
    decorated function. The "reads" decorator tracks the position of the cursor
    before and after the function is read and creates a parcel from those
    positions. 

    """
    def __init__(self, depvar):
        self.depvar = depvar
        self.parcels = []
        self.idx = 0
        # Track previously successfully parsed indexes to use as reset points. 
        self.checkpoints = []

    def reset_to(self, idx=None):
        """
        Reset the cursor to the given index and remove parcels which end after
        that index. 

        """
        if idx is None: idx = self.idx
        self.idx = idx
        self.parcels = [p for p in self.parcels if p.idx_end <= idx]

    def __repr__(self):
        return self.to_tree().__repr__()

    def look(self, options):
        """
        Try the given options and advance the cursor if one of them matches. 

        The options can be characters or functions. 

        """
        idx_prev = self.idx
        for option in options:
            if callable(option): option()
            # Match end of string with None. 
            elif self.idx >= len(self.depvar) and option is None: self.idx += 1
            elif self.idx >= len(self.depvar): return False
            elif self.depvar[self.idx] == option: self.idx += 1
            if self.idx > idx_prev: return True
        return False

    def read(self, options=[], exceptions=[], count_max=1, require=False, idx_reset=None):
        """
        Advance the cursor while the maximum number of matches has not yet been
        reached and the cursor position matches one of the options.

        If the require flag is given as a tuple containing the upper and lower
        bounds of a count range, respectively, then require options to be
        matched within the given count range. None means no limit. If the
        require keyword is set to True then the count range is set to (None,
        None,) as a default so all options must be matched in the order given.
        Returns true if the match count falls within the given count range,
        false otherwise. Resets the cursor position if the requirement is not
        met. 

        Args:
            - options: Options to match
            - exceptions: Patterns that stop consumption, for when two classes
              of syntax could be matched at once. 
            - count_max: Maximum number of matches (None for unlimited number
              of matches). Ignored if require option is given.
            - require: If the options are required, can be False, True, or a
              tuple of upper and lower bounds for number of matched options.
            - idx_reset: An index to reset the index to if the requirements are
              not met. Defaults to the previous checkpoint index taken by the
              reads decorator. 

        """
        idx_prev = self.idx

        if require != False:
            if require is True: require = (None,None,)
            count_min, count_max = require
            if idx_reset is None: 
                if self.checkpoints:
                    idx_reset = self.checkpoints[-1]
                else:
                    idx_reset = self.idx
            match_count = sum([self.look([option]) for option in options])
            met = not any((
                (count_min is not None and match_count < count_min),
                (count_max is not None and match_count > count_max),
                (require==(None,None,) and match_count != len(options))
            ))
            if not met: self.reset_to(idx_reset)
        else:
            count_cur = 0
            while count_max==None or count_cur<count_max:
                if self.look(exceptions): self.idx = idx_prev; break
                if not self.look(options): break
                count_cur+= 1
        return idx_prev < self.idx

    def reads(name):
        """
        Decorator to give token parsed by parsing function a name. 

        Allows for parsing higher-level syntax made up of smaller pieces of
        syntax. 

        """
        def decorator(func):
            @functools.wraps(func)
            def wrapper(self, *args, **kwargs):
                idx_prev = self.idx
                self.checkpoints.append(idx_prev)
                self.read(*args, options=[lambda: func(self)], **kwargs)
                self.checkpoints.pop()
                if idx_prev < self.idx and name: 
                    text = self.depvar[idx_prev:self.idx]
                    self.parcels.append(Parcel(idx_prev, self.idx, text, name))
            return wrapper
        return decorator

    @reads("AlphaLower")
    def lalpha(self): 
        self.read("abcdefghijklmnopqrstuvwxyz")

    @reads("AlphaUpper")
    def ualpha(self): 
        self.read("ABCDEFGHIJKLMNOPQRSTUVWXYZ")

    @reads("Digit")
    def digit(self): 
        self.read("1234567890")

    @reads("Whitespace")
    def whitespace(self): 
        self.read("\n\t ")

    @reads("Alpha")
    def alpha(self): 
        self.read([self.lalpha, self.ualpha])

    @reads("AlphaDig")
    def alphadig(self): 
        self.read([self.alpha, self.digit])

    @reads("UseName")
    def use_name(self): 
        r"""
        3.1.4 USE flag names

        A USE flag name may contain any of the characters [A-Za-z0-9+_@-]. It
        must begin with an alphanumeric character. Underscores should be
        considered reserved for USE_EXPAND, as described in section 11.1.1.

        Note: Usage of the at-sign is deprecated. It was previously required
        for LINGUAS.

        """
        if not self.read([self.alphadig], require=True): return
        self.read([self.alphadig, *"+_@-"], count_max=None)

    @reads("!Use")
    def use_not(self): 
        self.read("!")

    @reads("Use?")
    def useq(self): 
        self.read("?")

    @reads("UseQuery")
    def use_query(self):
        self.use_not()
        if not self.read([self.use_name], require=True): return
        if not self.read([self.useq], require=True): return

    @reads("gt")
    def gt(self): 
        self.read(">")

    @reads("lt")
    def lt(self): 
        self.read("<")

    @reads("eq")
    def eq(self): 
        self.read("=")

    @reads("ax")
    def ax(self): 
        self.read("~")

    @reads("gteq")
    def gteq(self):
        if not self.read([self.gt, self.eq], require=True): return

    @reads("lteq")
    def lteq(self):
        if not self.read([self.lt, self.eq], require=True): return

    @reads("VersionGate")
    def ver_gate(self): 
        r"""
        8.3.1 Operators

        The following operators are available:
        - < Strictly less than the specified version.
        - <= Less than or equal to the specified version.
        - = Exactly equal to the specified version. Special exception: if the
          version specified has an asterisk immediately following it, then only
          the given number of version components is used for com- parison, i.
          e. the asterisk acts as a wildcard for any further components. When
          an asterisk is used, the specification must remain valid if the
          asterisk were removed. (An asterisk used with any other operator is
          illegal.)
        - ~ Equal to the specified version when revision parts are ignored.
        - >= Greater than or equal to the specified version.
        - > Strictly greater than the specified version.

        """
        self.read([self.gteq, self.lteq, self.gt, self.lt, self.eq, self.ax])

    @reads("Bang")
    def bang(self): 
        self.read("!")

    @reads("SoftBlock")
    def soft_block(self): 
        self.read([self.bang])

    @reads("StrongBlock")
    def strong_block(self): 
        if not self.read([self.bang]*2, require=True): return

    @reads("Block")
    def block(self): 
        r"""
        8.3.2 Block operator

        If the specification is prefixed with one or two exclamation marks, the
        named dependency is a block rather than a requirement—that is to say,
        the specified package must not be installed. As an exception, weak
        blocks on the package version of the ebuild itself do not count. There
        are two strengths of block: weak and strong. A weak block may be
        ignored by the package manager, so long as any blocked package will be
        uninstalled later on. A strong block must not be ignored. The mapping
        from one or two exclamation marks to strength is described in table
        8.9.

        """
        self.read([self.strong_block, self.soft_block])

    @reads("VersionSep")
    def ver_sep(self): 
        self.read("-")

    @reads("VersionMajor")
    def ver_maj(self): 
        self.read([self.digit], count_max=None)

    @reads("VersionDelimiter")
    def ver_del(self): 
        self.read(".")
        
    @reads("VersionWildcard")
    def ver_op(self): 
        self.read("*")

    @reads("VersionMinor")
    def ver_min(self): 
        if not self.read([self.ver_del], require=True): return
        self.read([self.digit], count_max=None)

    @reads("VersionNumber")
    def ver_num(self):
        if not self.read([self.ver_maj], require=True): return
        self.read([self.ver_min], count_max=None)
        self.ver_op()

    @reads("VersionLetter")
    def ver_letter(self): 
        self.alpha()

    @reads("VersionReleaseSep")
    def ver_rel_sep(self): 
        self.read("_")

    @reads("VersionReleasePrefix")
    def ver_rel_prefix(self): 
        self.read([self.alpha], count_max=None)

    @reads("VersionReleaseSuffix")
    def ver_rel_suffix(self): 
        self.read([self.digit], count_max=None)

    @reads("VerEnd")
    def ver_end(self): 
        self.read([*")", self.whitespace, None])

    @reads("VersionRelease")
    def ver_release(self):
        if not self.read(
            [self.ver_rel_sep, self.ver_rel_prefix], require=True): return
        self.ver_rel_suffix()

    @reads("VersionRevision")
    def ver_revision(self): 
        if not self.read([self.ver_sep, self.alpha], require=True): return
        self.read([self.digit], count_max=None)

    @reads("Version")
    def version(self):
        r"""
        3.2 Version Specifications

        The package manager must neither impose fixed limits upon the number of
        version components, nor upon the length of any component. Package
        managers should indicate or reject any version that is invalid
        according to the rules below.

        A version starts with the number part, which is in the form
        [0-9]+(\.[0-9]+)* (an unsigned integer, followed by zero or more
        dot-prefixed unsigned integers).

        This may optionally be followed by one of [a-z] (a lowercase letter).

        This may be followed by zero or more of the suffixes _alpha, _beta,
        _pre, _rc or _p, each of which may optionally be followed by an
        unsigned integer. Suffix and integer count as separate version
        components.

        This may optionally be followed by the suffix -r followed immediately
        by an unsigned integer (the “revision number”). If this suffix is not
        present, it is assumed to be -r0.

        # EXTRA NOTE: the start of a version is marked with a dash '-'. 

        """
        if not self.read([self.ver_sep, self.ver_num], require=True): return
        self.ver_letter()
        self.read([self.ver_release], count_max=None)
        self.ver_revision()
        # if not self.read([self.ver_end], require=True): return

    @reads("PkgChar")
    def pkg_char(self): 
        self.read([*"+_-", self.alphadig], [self.version])

    @reads("PkgChar")
    def pkg_char_first(self): 
        self.read([*"_", self.alphadig])

    @reads("PackageName")
    def pkg_name(self):
        r"""
        3.1.2 Package names

        A package name may contain any of the characters [A-Za-z0-9+_-]. It
        must not begin with a hyphen or a plus sign, and must not end in a
        hyphen followed by anything matching the version syntax described in
        section 3.2.

        Note: A package name does not include the category. The term qualiﬁed
        package name is used where a category/package pair is meant. 

        # EXTRA NOTE: the category requirement is not enforced by the parser
        # here. 

        """
        if not self.read([self.pkg_char_first], require=True): return
        self.read([self.pkg_char], count_max=None)

    @reads("CatPkgDelim")
    def catpkg_delim(self): 
        self.read("/")

    @reads("CatChar")
    def cat_char_first(self):
        self.read([*"_", self.alphadig])

    @reads("CatChar")
    def cat_char(self):
        self.read([*"+_.-", self.alphadig])

    @reads("CategoryName")
    def cat_name(self): 
        r"""
        3.1.1 Category names

        A category name may contain any of the characters [A-Za-z0-9+_.-]. It
        must not begin with a hyphen, a dot or a plus sign.

        """
        if not self.read([self.cat_char_first], require=True): return
        self.read([self.cat_char], count_max=None)

    @reads("CatPkg")
    def catpkg(self):
        r"""
        """
        self.read([self.cat_name, self.catpkg_delim], require=True)
        self.pkg_name()

    @reads("SlotSep")
    def slot_sep(self): 
        self.read(":")

    @reads("SlotChar")
    def slot_char_first(self): 
        self.read([*"_", self.alphadig])

    @reads("SlotChar")
    def slot_char(self): 
        self.read([*"+_.-", self.alphadig])

    @reads("SlotOp")
    def slot_op(self): 
        self.read("*=")

    @reads("SlotBase")
    def slot_base(self): 
        if not self.read([self.slot_char_first], require=True): return
        self.read([self.slot_char], count_max=None)

    @reads("SubslotSep")
    def subslot_sep(self): 
        self.read("/")

    @reads("Subslot")
    def subslot(self):
        idx_prev = self.idx
        if not self.read([self.subslot_sep], require=True): return
        self.slot_base()

    @reads("Slot")
    def slot(self):
        r"""
        8.3.3 Slot dependencies

        A named slot dependency consists of a colon followed by a slot name. A
        specification with a named slot dependency matches only if the slot of
        the matched package is equal to the slot specified. If the slot of the
        package to match cannot be determined (e. g. because it is not a
        supported EAPI), the match is treated as unsuccessful.

        In EAPIs shown in table 8.7 as supporting sub-slots, a slot dependency
        may contain an optional sub-slot part that follows the regular slot and
        is delimited by a / character. An operator slot dependency consists of
        a colon followed by one of the following operators:
        - * Indicates that any slot value is acceptable. In addition, for
          runtime dependencies, indicates that the package will not break if
          the matched package is uninstalled and replaced by a different
          matching package in a different slot.
        - = Indicates that any slot value is acceptable. In addition, for
          runtime dependencies, indicates that the package will break unless a
          matching package with slot and sub-slot equal to the slot and
          sub-slot of the best version installed as a build-time (DEPEND)
          dependency is available.
        - slot= Indicates that only a specific slot value is acceptable, and
          otherwise behaves identically to the plain equals slot operator.

        To implement the equals slot operator, the package manager will need to
        store the slot/sub-slot pair of the best installed version of the
        matching package. This syntax is only for package manager use and must
        not be used by ebuilds. The package manager may do this by inserting
        the appropriate slot/sub-slot pair between the colon and equals sign
        when saving the package’s dependencies. The sub-slot part must not be
        omitted here (when the SLOT variable omits the sub-slot part, the
        package is considered to have an implicit sub-slot which is equal to
        the regular slot). Whenever the equals slot operator is used in an
        enabled dependency group, the dependencies (DEPEND) must ensure that a
        matching package is installed at build time. It is invalid to use the
        equals slot operator inside PDEPEND or inside any-of dependency
        specifications.

        3.1.3 Slot names

        A slot name may contain any of the characters [A-Za-z0-9+_.-]. It must
        not begin with a hyphen, a dot or a plus sign.
        """
        if not self.read([self.slot_sep], require=True): return
        self.slot_base()
        self.subslot()
        self.slot_op()

    @reads("UseDefaultOpen")
    def use_default_open(self): 
        self.read("(")

    @reads("UseDefaultClose")
    def use_default_close(self): 
        self.read(")")

    @reads("UseDefault")
    def use_default(self):
        if not self.read([self.use_default_open], require=True): return
        self.read("+-")
        if not self.read([self.use_default_close], require=True): return

    @reads("UseDependencySep")
    def use_dep_sep(self): 
        self.read(",")

    @reads("UseDependencyNot")
    def use_dep_not(self): 
        self.read("-")

    @reads("UseDependencyNotIf")
    def use_dep_not_if(self): 
        self.read("!")

    @reads("UseDependencyNot")
    def use_dep_eq(self): 
        self.eq()

    @reads("UseDependency")
    def use_dep(self):
        self.use_dep_sep()
        self.read([self.use_dep_not, self.use_dep_not_if], count_max=1)
        if not self.read([self.use_name], require=True): return
        self.use_default()
        self.read([self.use_dep_eq, self.useq], count_max=1)

    @reads("UseDependencyOpen")
    def use_deps_open(self): 
        self.read("[")

    @reads("UseDependencyClose")
    def use_deps_close(self):
        self.read("]")

    @reads("UseDependencies")
    def use_deps(self):
        r"""
        8.3.4 2-style and 4-style USE dependencies

        A 2-style or 4-style use dependency consists of one of the following:
        - [opt] The flag must be enabled.
        - [opt=] The flag must be enabled if the flag is enabled for the
          package with the dependency, or disabled otherwise.
        - [!opt=] The flag must be disabled if the flag is enabled for the
          package with the dependency, or enabled otherwise.
        - [opt?] The flag must be enabled if the flag is enabled for the
          package with the dependency.
        - [!opt?] The flag must be disabled if the use flag is disabled for the
          package with the dependency.
        - [-opt] The flag must be disabled.

        Multiple requirements may be combined using commas, e. g.
        [first,-second,third?]. When multiple requirements are specified, all
        must match for a successful match. In a 4-style use dependency, the
        flag name may immediately be followed by a default specified by either
        (+) or (-). The former indicates that, when applying the use dependency
        to a package that does not have the flag in question in
        IUSE_REFERENCEABLE, the package manager shall behave as if the flag
        were present and enabled; the latter, present and disabled. Unless a
        4-style default is specified, it is an error for a use dependency to be
        applied to an ebuild which does not have the flag in question in
        IUSE_REFERENCEABLE. Note: By extension of the above, a default that
        could reference an ebuild using an EAPI not support- ing profile IUSE
        injections cannot rely upon any particular behaviour for flags that
        would not have to be part of IUSE. It is an error for an ebuild to use
        a conditional use dependency when that ebuild does not have the flag in
        IUSE_EFFECTIVE.

        """
        if not self.read([self.use_deps_open], require=True): return
        self.read([self.use_dep], count_max=None)
        if not self.read([self.use_deps_close], require=True): return

    @reads("Atom")
    def atom(self):
        self.block()
        self.ver_gate()
        if not self.read([self.catpkg], require=True): return
        self.version()
        self.slot()
        self.use_deps()
        self.read([self.whitespace], count_max=None)

    @reads("GroupOpen")
    def group_open(self): 
        self.read("(")

    @reads("GroupClose")
    def group_close(self): 
        self.read(")")

    @reads("AllOfGroup")
    def all_of_group(self):
        r"""
        8.2 Dependency Specification Format

        An all-of group, which consists of an open parenthesis, followed by
        whitespace, followed by one or more of (a dependency item of any kind
        followed by whitespace), followed by a close parenthesis. More
        formally: all-of ::= ’(’ whitespace (item whitespace)+ ’)’. Permitted
        in all specification style variables.

        # EXTRA NOTE: the whitespace requirement is not enforced by the parser
        # here. 

        """
        self.read([self.whitespace],count_max=None)
        if not self.read([self.group_open], require=True): return
        self.read([self.whitespace],count_max=None)
        self.read([self.meta_group_item], count_max=None)
        self.read([self.whitespace], count_max=None)
        if not self.read([self.group_close], require=True): return
        self.read([self.whitespace],count_max=None)
        
    @reads("AnyOfGroupSymbol")
    def any_of_group_symbol(self): 
        self.read([lambda: self.read("|")]*2, require=True)

    @reads("AnyOfGroup")
    def any_of_group(self):
        r"""
        8.2 Dependency Specification Format

        An any-of group, which consists of the string ||, followed by
        whitespace, followed by an open parenthesis, followed by whitespace,
        followed by one or more of (a dependency item of any kind followed by
        whitespace), followed by a close parenthesis. More formally: any-of ::=
        ’||’ whitespace ’(’ whitespace (item whitespace)+ ’)’. Permitted in
        DEPEND, BDEPEND, RDEPEND, PDEPEND, IDEPEND, LICENSE, REQUIRED_USE.

        # EXTRA NOTE: the whitespace requirement is not enforced by the parser
        # here. 

        """
        if not self.read([self.any_of_group_symbol], require=True): return
        self.read([self.whitespace],count_max=None)
        if not self.read([self.group_open], require=True): return
        self.read([self.whitespace],count_max=None)
        self.read([self.meta_group_item], count_max=None)
        self.read([self.whitespace],count_max=None)
        if not self.read([self.group_close], require=True): return
        self.read([self.whitespace],count_max=None)

    @reads("ExactlyOneOfGroupSymbol")
    def exactly_one_of_group_symbol(self): 
        self.read([*"^^"], require=True)

    @reads("ExactlyOneOfGroup")
    def exactly_one_of_group(self):
        r"""
        8.2 Dependency Specification Format

        An exactly-one-of group, which has the same format as the any-of group, but
        begins with the string ^^ instead. Permitted in REQUIRED_USE.

        # EXTRA NOTE: the whitespace requirement is not enforced by the parser
        # here. 

        """
        if not self.read([self.exactly_one_of_group_symbol], require=True):
            return
        self.read([self.whitespace],count_max=None)
        if not self.read([self.group_open], require=True): return
        self.read([self.whitespace],count_max=None)
        self.read([self.meta_group_item], count_max=None)
        self.read([self.whitespace],count_max=None)
        if not self.read([self.group_close], require=True): return
        self.read([self.whitespace],count_max=None)

    @reads("MostOneOfGroupSymbol")
    def most_one_of_group_symbol(self): 
        self.read([lambda: self.read("?")]*2, require=True)

    @reads("MostOneOfGroup")
    def most_one_of_group(self):
        r"""
        8.2 Dependency Specification Format

        An at-most-one-of group, which has the same format as the any-of group,
        but begins with the string ?? instead. Permitted in REQUIRED_USE in
        EAPIs listed in table 8.5 as supporting REQUIRED_USE ?? groups.

        # EXTRA NOTE: the whitespace requirement is not enforced by the parser
        # here. 

        """
        if not self.read([self.most_one_of_group_symbol], require=True): return
        self.read([self.whitespace],count_max=None)
        if not self.read([self.group_open], require=True): return
        self.read([self.whitespace],count_max=None)
        self.read([self.meta_group_item], count_max=None)
        self.read([self.whitespace],count_max=None)
        if not self.read([self.group_close], require=True): return
        self.read([self.whitespace],count_max=None)

    @reads("DynamicUseOpen")
    def dynamic_use_open(self): 
        self.read("(")

    @reads("DynamicUseClose")
    def dynamic_use_close(self): 
        self.read(")")

    @reads("DynamicUse")
    def dynamic_use(self):
        r"""
        8.2 Dependency Specification Format

        A use-conditional group, which consists of an optional exclamation
        mark, followed by a use flag name, followed by a question mark,
        followed by whitespace, followed by an open parenthesis, followed by
        whitespace, followed by one or more of (a dependency item of any kind
        followed by whitespace), followed by a close parenthesis. More
        formally: use-conditional ::= ’!’? flag-name ’?’ whitespace ’(’
        whitespace (item whitespace)+ ’)’. Permitted in all specification style
        variables.

        # EXTRA NOTE: the whitespace requirement is not enforced by the parser
        # here. 

        """
        if not self.read([self.use_query], require=True): return
        self.read([self.whitespace], count_max=None)
        if not self.read([self.dynamic_use_open], require=True): return
        self.read([self.whitespace], count_max=None)
        self.read([self.meta_group_item], count_max=None)
        self.read([self.whitespace], count_max=None)
        if not self.read([self.dynamic_use_close], require=True): return
        self.read([self.whitespace], count_max=None)

    def meta_group_item(self):
        self.read([
            self.dynamic_use, 
            self.all_of_group, 
            self.any_of_group, 
            self.exactly_one_of_group, 
            self.most_one_of_group, 
            self.atom
        ])

    @reads("Root")
    def root(self): 
        r"""
        Parse atom dependency list. 

        """
        self.read([
            self.all_of_group, 
            self.any_of_group, 
            self.exactly_one_of_group, 
            self.most_one_of_group, 
            self.dynamic_use, 
            self.atom
        ], count_max=None)

    def to_tree(self):
        """
        Convert the list of parsed parcels to a tree and return that tree. 

        """
        in_tree = lambda a,o: (
            a.data.idx_start >= o.data.idx_start and \
            a.data.idx_end <= o.data.idx_end)
        trees = [Tree(parcel) for parcel in self.parcels]
        trees.reverse()
        trees.sort(key=lambda t: (t.data.idx_start, -t.data.idx_end))
        roots = []
        ancestry = []
        for tree in trees:
            while ancestry and not in_tree(tree, ancestry[-1]): ancestry.pop()
            if ancestry:
                ancestry[-1].add_branch(tree)
            else:
                roots.append(tree)
            ancestry.append(tree)
        if not roots:
            return Tree(Parcel(0,0,"",""))
        return roots[0]


class Rdeps:
    """
    Provides a pipeline for parsing the dependency list given by the following
    command: 
    emerge --pretend --verbose --emptytree --depclean > ~/emerge_rdeps.txt

    Provides dependees_by_dependency attribute which maps a dependency name
    to a list of dependees for that dependency.
    
    """
    def __init__(self, filepath):
        self.dependees_by_dependency = \
            self._build_dependee_dict( \
            self._extract_lines( \
            self._read_file( \
            filepath)))

    def _read_file(self, filepath):
        """
        Read the file.

        """
        if not filepath:
            return
        with open(filepath) as f:
            text = f.read()
        return text

    def _extract_lines(self, text):
        """
        Extract the relevant lines from the file.

        """
        if text is None:
            command = "emerge --pretend --verbose --emptytree --depclean"
            process = subprocess.Popen(
                command, 
                stdout=subprocess.PIPE, 
                shell=True, 
                text=True
            )
            stdout, stderr = process.communicate()
            text = stdout
        is_blank = lambda line: not line.strip()
        lines = text.split("\n")
        start_token = "pulled in by:"
        end_token = ">>>"
        start_flag = False
        end_flag = False

        filtered_lines = []
        for line in lines:
            if not start_flag: start_flag = line.endswith(start_token)
            if start_flag: end_flag = line.startswith(end_token)
            else: continue
            if end_flag: break
            if is_blank(line): continue
            filtered_lines.append(line)
        return filtered_lines

    def _build_dependee_dict(self, lines):
        """
        Create a dictionary mapping each dependency to a list of packages which
        depend on it. 

        """
        dependees_by_dependency = {}

        parent_indent = 0
        parent_dependee_pkgname = ""
        for line in lines:
            line_indent = len(line) - len(line.lstrip())
            line_pkgname = line.strip().split(" ")[0]

            if (not parent_indent) or (line_indent <= parent_indent):
                parent_indent = line_indent
                parent_pkgname = line_pkgname
            else: 
                dependees_by_dependency.setdefault(parent_pkgname, [])
                dependees_by_dependency[parent_pkgname].append(line_pkgname)
        return dependees_by_dependency

class Colored:
    """
    Store text along with a color. Represent that text with the escape
    sequences to print the text in that color embedded. 

    """
    # for i in {0..15}; do s="Hello, World!"; echo -e "\033[38;5;""$i""m""$s""\033[0m"; done;
    def __init__(self, text, color):
        if isinstance(text, Colored):
            text = text.text

        if isinstance(color, str):
            color = {
                "black": 0,
                "red": 1,
                "green": 2,
                "yellow": 3,
                "blue": 4,
                "magenta": 5,
                "cyan": 6,
                "white": 7,
                "bright_black": 8,
                "bright_red": 9,
                "bright_green": 10,
                "bright_yellow": 11,
                "bright_blue": 12,
                "bright_magenta": 13,
                "bright_cyan": 14,
                "bright_white": 15,
            }[color]
        self.color = color
        self.text = text

    def __repr__(self):
        return f"\033[38;5;{self.color}m{self.text}\033[0m"

class Triggers:
    """
    Provides functions to construct a tree detailing the reason for a package
    to be installed. 

    """
    depvar_names="DEPEND RDEPEND BDEPEND IDEPEND PDEPEND"
    def __init__(self, rdeps, use_full_atom=False, pkgname=None):
        self.full_atom = use_full_atom
        self.dependees_by_dependency = rdeps.dependees_by_dependency
        if pkgname is None:
            self.pkgname = self.prompt_pkgname()


    def prompt_pkgname(self, opts=None):
        """
        Prompt for a package name from a given list of package names. Provide
        options if input matches multiple pkgnames. 

        """
        pkgnames = self.dependees_by_dependency.keys()
        if opts is None:
            opts = []
        elif opts:
            print("Input option number.")
        else:
            print("Input atom name (regex), returns matching atoms.")

        for i,opt in enumerate(opts):
            print(i,opt)
        user_input = input(">>> ")
        try:
            user_regex = re.compile(user_input)
        except re.error:
            print("Invalid regex. Reprompting.")
            return self.prompt_pkgname(opts)

        if opts and user_input.isdigit(): return list(opts)[int(user_input)]
        elif opts: return self.prompt_pkgname(opts)

        for pkgname in pkgnames:
            if user_regex.search(pkgname): opts.append(pkgname)

        opts = sorted(list(opts))
        if len(opts) == 1:
            return opts[0]
        return self.prompt_pkgname(opts)

    def _calc_rdep_levels(
            self, pkgname, _seen=None, _level=0):
        """
        Given a package name and a dictionary of dependees, generate tuples
        containing the level and name of each dependee for the given package name. 

        """
        atom_group_prefix = "@"

        if _seen is None: _seen = []
        yield (_level,pkgname,)

        for dependency_name in self.dependees_by_dependency.get(pkgname,[]):
            if dependency_name in _seen: continue
            if not dependency_name.startswith(atom_group_prefix):
                _seen.append(dependency_name)
            yield from self._calc_rdep_levels(
                dependency_name,
                _seen=_seen, 
                _level=_level+1)

    def _get_atom_pkgname(self, catpkg_text):
        """
        Given a full catpkg string, parse it and return only the catpkg as a
        string without the version, slot, and other appendages. 

        """
        if catpkg_text.startswith("@"):
            return catpkg_text
        x = lambda d: d.kind
        parser = Parser(catpkg_text)
        parser.root()
        tree = parser.to_tree()
        pkgname = tree.traverse_branches(
            ["Atom", "CatPkg", 0], x)[0].data.value.strip()
        return pkgname

    def _get_depvars(self, pkgname):
        """
        Given a package name, search for that package's dependencies with
        portageq. Return a list of dependencies for each dependency type in the
        self.depvar_names attribute. 

        """
        command = f"portageq metadata / ebuild {pkgname} {self.depvar_names}"
        process = subprocess.Popen(command, stderr=subprocess.PIPE, stdout=subprocess.PIPE, shell=True, text=True)
        stdout, stderr = process.communicate()
        if stderr:
            print(stderr)
            quit()
        depvars = stdout.split("\n")
        return depvars 

    def _make_trigger_tree(self, tree, triggers=None):
        """
        Given the parse tree for a dependency variable, create a hierarchical
        tree that organizes all atoms in the dependency variable as branches of
        the groups which would trigger their installation. 

        """
        x = lambda d: d.kind

        if triggers is None:
            triggers = Tree(("Root", tree.data.value.strip(),))
        atoms = tree.traverse_branches(["Atom"], x)

        group_types = [
            "MostOneOfGroup",
            "ExactlyOneOfGroup",
            "AnyOfGroup",
            "AllOfGroup",
        ]

        for group in group_types:
            for branch in tree.traverse_branches([group],x):
                text = branch.data.value.strip()
                b = Tree((group, text,))
                triggers.add_branch(b)
                self._make_trigger_tree(branch, b)

        # Dynamic use statements must be handled differently than other groups.
        for branch in tree.traverse_branches(["DynamicUse"],x):
            use_query = branch.traverse_branches(["UseQuery"], x)
            use_query = use_query[0].data.value
            b = Tree(("DynamicUse", use_query))
            triggers.add_branch(b)
            self._make_trigger_tree(branch, b)

        for branch in atoms:
            if self.full_atom:
                pkgname = branch.data.value
            else:
                pkgname = branch.traverse_branches(["CatPkg"], x)
                pkgname = pkgname[0].data.value
                pkgname = self._get_atom_pkgname(pkgname)
            triggers.add_branch(Tree(("Pkgname", pkgname,)))
        return triggers

    def _prune_trigger_tree(self, trigger_tree, pkgname):
        """
        Given a trigger tree and a package name, remove all branches of the
        tree that do not end withq the package name. 

        """
        ax = []
        for i,branch in enumerate(trigger_tree.branches):
            flag = self._prune_trigger_tree(branch, pkgname)
            if not flag:
                ax.append(i)
        trigger_tree.remove_branches(ax)
        if trigger_tree.data[0] == "Pkgname" and self._get_atom_pkgname(trigger_tree.data[1]) == pkgname:
            return trigger_tree
        if not trigger_tree.branches:
            return False
        return trigger_tree

    def examine_dependencies(self):
        """
        Given a package name, obtain the hierarchy of dependees for that
        package, get the dependency variables for each type of dependency for
        that package, assemble the syntax that triggers the installation of the
        previous dependency for each dependee, and return this as a three level
        tree with the first level being a tuple consisting of the depth level
        and package name of the dependendee in question, the dependency
        variables being searched, and the depend variable syntax which results
        in the previous dependency being pulled in. Yield each of these trees.

        """
        rdep_levels = list(self._calc_rdep_levels(self.pkgname))
        ancestors = {}
        level,pkgname = rdep_levels.pop(0)
        pkgname = self._get_atom_pkgname(pkgname)
        ancestors[level] = pkgname
        trigger = Tree((level, pkgname,))
        yield(trigger)

        for level,pkgname in rdep_levels:
            trigger = Tree((level,pkgname,))
            if pkgname.startswith("@"):
                yield(trigger)
                continue

            pkg_depvars = self._get_depvars(pkgname)
            ancestors[level] = self._get_atom_pkgname(pkgname)
            for depend_var,depend_str in zip(self.depvar_names.split(" "),pkg_depvars):
                parser = Parser(depend_str)
                parser.root()
                tree = parser.to_tree() 
                triggers = self._make_trigger_tree(tree)
                triggers = self._prune_trigger_tree(triggers, ancestors[level-1])
                if not triggers: continue
                trigger.add_branch(Tree((depend_var, triggers,)))
            yield(trigger)

    def trigger_tree_to_lines(self, trigger_tree,lines=None, level=0):
        """
        Convert a trigger tree to a list of output lines. 

        """
        if lines is None: lines = []
        if not trigger_tree.data[0] in ("Root", "AllOfGroup"):
            lines.append((level,trigger_tree.data[1],))
        for branch in trigger_tree.branches:
            self.trigger_tree_to_lines(branch, lines=lines,level=level+1)
        return lines

    def repr_trigger(self, trigger):
        """
        Convert a trigger to a list of colored output lines. 

        """
        indent = 2
        level,pkgname = trigger.data
        if pkgname.startswith("@"):
            pkgname = Colored(pkgname, 'green')
        else:
            pkgname = Colored(pkgname, 'yellow')

        lines = []
        lines.append(f"{' '*indent*level}{pkgname}")
        for branch in trigger.branches:
            depvar_name,trigger_tree = branch.data
            trigger_lines = self.trigger_tree_to_lines(trigger_tree)
            lines.append(f"{' '*indent*level}|  {Colored('-','bright_black')} {Colored(depvar_name,'bright_black')}:")
            for _level,trigger_line in trigger_lines:
                lines.append(f"{' '*indent*level}|{' '*(indent*_level+4)}{trigger_line}")
        return "\n".join(lines)

    def print(self):
        """
        Print the output tree. 
        
        """
        rdep_tree = self.examine_dependencies()
        for trigger in rdep_tree:
            print(self.repr_trigger(trigger))

def main():
    filepath = "".join(sys.argv[1:2])
    rdeps = Rdeps(filepath)
    triggers = Triggers(rdeps)
    triggers.print()


if __name__ == '__main__':
    main()
