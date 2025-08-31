from gentoo_rdep_analyzer.rdep_analyzer import *
import pytest
from pytest import param

def test_tree():
    level_lens = [10,10]

    def data_func(*args):
        result = 0
        for i,arg in enumerate(reversed(args)):
            result+=arg*(10**i) 
        return result

    def make_tree(level_lens, level, args, tree, output=None):
        if output is None: output = [" "*tree.indent_inc*level+str(tree.data)]
        if not level_lens: return tree
        level += 1
        args.append(None)
        for i in range(level_lens[0]):
            args[-1] = i
            data = data_func(*args)
            t = Tree(data)
            output.append(" "*tree.indent_inc*level+str(data))
            make_tree(
                level_lens[1:], 
                level, 
                [i for i in args], 
                t, 
                output)
            tree.add_branch(t)
        return tree,output

    def check_branch_length(level_lens, tree):
        if not level_lens: return
        assert len(tree.branches) == level_lens[0]
        for branch in tree.branches:
            check_branch_length(level_lens[1:], branch)

    tree,output = make_tree(level_lens, 0, [], Tree())
    check_branch_length(level_lens, tree)

    tree_repr = tree.__repr__()
    assert "\n".join(output) == tree_repr

def test_tree_init():
    tree = Tree()
    assert tree.data is None
    assert tree._root is None
    assert tree.branches == []
    tree = Tree("root")
    assert tree.data == "root"

def test_tree_add_branch():
    tree = Tree()
    branch = Tree("branch")
    tree.add_branch(branch)
    assert branch in tree.branches
    assert branch._root is tree

def test_tree_repr():
    tree = Tree()
    tree1 = Tree("tree1")
    tree2 = Tree("tree2")
    tree11 = Tree("tree11")
    tree.add_branch(tree1)
    tree.add_branch(tree2)
    tree1.add_branch(tree11)
    expected_output = (
        "None\n"
        "  tree1\n"
        "    tree11\n"
        "  tree2"
    )
    assert tree.__repr__() == expected_output

def test_tree_traverse():
    tree = Tree()
    text = "one two three four five six seven eight one two three two three three"
    for word in text.split(" "):
        branch = Tree(word)
        tree.add_branch(branch)
        for char in word:
            branch_2 = Tree(char)
            branch.add_branch(branch_2)
    # Select one from a list
    branch = tree.traverse_branches(["one", 0], lambda x: x)
    assert len(branch) == 1
    assert branch[0].data == "one"
    # Select a list
    branch = tree.traverse_branches(["one"], lambda x: x)
    assert len(branch) == 2
    # Select using more complex key function
    branch = tree.traverse_branches(["5", 1], lambda x: str(len(x)))
    assert len(branch) == 1
    assert branch[0].data == "seven"

def test_parser_init():
    depvar = "category/atom"
    parser = Parser(depvar)
    assert parser.depvar == depvar

def test_parser_reset():
    depvar = "cat/pkg"
    parser = Parser(depvar)
    parser.catpkg()
    for i in range(len(depvar)):
        reset_point = len(depvar)-i
        parser.reset_to(reset_point)
        key_func = lambda x: x.idx_end
        assert max(parser.parcels, key=key_func).idx_end <= reset_point
    parser.idx = 2
    parser.parcels = [Parcel(0,1,"c","test"), Parcel(1,3,"at","test")]
    parser.reset_to()
    assert str(parser.parcels) == str([Parcel(0,1,"c","test")])

def test_parser_look_with_chars():
    depvar = "depvar"
    parser = Parser(depvar)

    parser.look("d")
    assert parser.idx == 1
    assert parser.parcels == []

    parser.look("v")
    assert parser.idx == 1
    assert parser.parcels == []

def test_parser_look_with_funcs():
    depvar = "depvar"
    parser = Parser(depvar)

    def match():
        parser.alpha()

    assert parser.look([match]) == True
    assert parser.idx == 1

def test_parser_read_normal():
    depvar = "cat/pkg"
    parser = Parser(depvar)
    parser.read("cat")
    assert parser.idx == 1

def test_parser_read_exception():
    def letter_number():
        parser.alpha()
        parser.digit()
    depvar = "dc1"
    parser = Parser(depvar)
    parser.read("c", exceptions=[letter_number])
    assert parser.idx == 0

def test_parser_read_count():
    depvar = "abcdefghijklmnopqrstuvwxyz"
    parser = Parser(depvar)
    parser.read([parser.alpha], count_max=4)
    assert parser.idx == 4
    parser.read([parser.alpha], count_max=None)
    assert parser.idx == len(depvar)

def test_parser_read_require():
    depvar = "abc123"
    parser = Parser(depvar)
    parser.read([parser.alpha]*3, require=True)
    assert parser.idx == 3
    parser.read([parser.alpha]*3, require=True)
    assert parser.idx == 3
    parser.read([parser.digit]*5, require=True)
    assert parser.idx == 3
    parser.read([parser.digit]*5, require=True, idx_reset=0)
    assert parser.idx == 0
    parser.read([parser.alphadig]*len(depvar), require=(1,None))
    assert parser.idx == len(depvar)
    
def test_parser_reads():
    depvar = "__private123"
    parser = Parser(depvar)

    @Parser.reads("Private")
    def private(self):
        self.read("__", require=True)
        self.read([parser.alpha], require=True)
        self.read([parser.alphadig], count_max=None)

    private(parser)
    tree = parser.to_tree()
    assert tree.data.value == depvar
    assert tree.data.kind == "Private"
    assert parser.idx == len(depvar)

@pytest.mark.parametrize("depvar,expected",[
    param("alpha","alpha", id="default"),
    param("ALPHA","ALPHA", id="upper"),
    param("cat10","cat10", id="end with number"),
    param("c@t","c@t", id="@ symbol"),
    param("c_t","c_t", id="_ symbol"),
    param("c-t","c-t", id="- symbol"),
    param("c+t","c+t", id="+ symbol"),
    param("ca@","ca@", id="end with symbol"),
    param("_at","", id="cannot start with _ symbol"),
    param("-at","", id="cannot start with - symbol"),
    param("+at","", id="cannot start with + symbol"),
    param("@at","", id="cannot start with @ symbol"),
    param("*at","", id="cannot contain other symbol"),
])
def test_parser_usename(depvar, expected):
    r"""
    3.1.4 USE flag names

    A USE flag name may contain any of the characters [A-Za-z0-9+_@-]. It
    must begin with an alphanumeric character. Underscores should be
    considered reserved for USE_EXPAND, as described in section 11.1.1.

    Note: Usage of the at-sign is deprecated. It was previously required
    for LINGUAS.

    """
    parser = Parser(depvar)
    parser.use_name()
    value = next((p.value for p in parser.parcels if p.kind=="UseName"), "")
    assert value == expected

@pytest.mark.parametrize("depvar,expected",[
    param("<","<", id="less than"),
    param("<=","<=", id="less than or equal to"),
    param("=","=", id="equal to"),
    param("~","~", id="approximately"),
    param(">=",">=", id="greater than or equal to"),
    param(">",">", id="greater than"),
    param("*","", id="illegal version operator"),
])
def test_parser_vergate(depvar, expected):
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
    parser = Parser(depvar)
    parser.ver_gate()
    value = next((p.value for p in parser.parcels if p.kind == "VersionGate"),"")
    assert value == expected


@pytest.mark.parametrize("depvar,expected,subkind",[
    param("!", "!", "SoftBlock", id="soft block"),
    param("!!", "!!", "StrongBlock", id="strong block"),
])
def test_parser_block(depvar, expected, subkind):
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
    parser = Parser(depvar)
    parser.block()
    value = next((p.value for p in parser.parcels if p.kind == "Block"),"")
    assert value == expected

    soft_block = [p for p in parser.parcels if p.kind == "SoftBlock"]
    strong_block = [p for p in parser.parcels if p.kind == "StrongBlock"]
    assert len(soft_block) == int(subkind == "SoftBlock")
    assert len(strong_block) == int(subkind == "StrongBlock")

@pytest.mark.parametrize("depvar,expected",[
    param("-","", id="must not match single hyphen"),
    param("-1","-1", id="major version"),
    param("-1.0","-1.0", id="minor version"),
    param("-.0","", id="major version is required"),
    param("-10","-10", id="big major version"),
    param("-10.10","-10.10", id="big minor version"),
    param("-1.2.33","-1.2.33", id="sub minor versions"),
    param("-1a","-1a", id="followed by letter"),
    param("-1ab","-1a", id="cannot be followed by multiple letters"),
    param("-1_alpha","-1_alpha", id="suffix"),
    param("-1_alpha1","-1_alpha1", id="suffix with integer"),
    param("-1_xyz","-1_xyz", id="non standard suffixes accepted here"),
    param("-1-r","-1-r", id="revision"),
    param("-1-r1","-1-r1", id="revision with number"),
])
def test_parser_version(depvar, expected):
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
    parser = Parser(depvar)
    parser.version()
    value = next((p.value for p in parser.parcels if p.kind == "Version"),"")
    assert value == expected

@pytest.mark.parametrize("depvar,expected",[
    param("alpha","alpha", id="default"),
    param("ALPHA","ALPHA", id="upper"),
    param("pkg10","pkg10", id="end with number"),
    param("p@g","p", id="illegal symbol"), # Should this behave like this?
    param("p_g","p_g", id="_ symbol"),
    param("p-g","p-g", id="- symbol"),
    param("p+g","p+g", id="+ symbol"),
    param("pk+","pk+", id="end with symbol"),
    param("_kg","_kg", id="can start with _ symbol"),
    param("-kg","", id="cannot start with - symbol"),
    param("+kg","", id="cannot start with + symbol"),
    param("*kg","", id="cannot contain other symbol"),
    param("pkg-","pkg-", id="end with hyphen only"),
    param("pkg-1.0","pkg", id="end with version"),
])
def test_parser_pkgname(depvar, expected):
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
    parser = Parser(depvar)
    parser.pkg_name()
    value = next((p.value for p in parser.parcels if p.kind=="PackageName"), "")
    assert value == expected

@pytest.mark.parametrize("depvar,expected",[
    param("alpha","alpha", id="default"),
    param("ALPHA","ALPHA", id="upper"),
    param("cat10","cat10", id="end with number"),
    param("c@t","c", id="illegal symbol"), # Should this behave like this. 
    param("c+t","c+t", id="+ symbol"),
    param("c_t","c_t", id="_ symbol"),
    param("c.t","c.t", id=". symbol"),
    param("c-t","c-t", id="- symbol"),
    param("ca.","ca.", id="end with symbol"),
    param("_at","_at", id="can start with _ symbol"),
    param("-at","", id="cannot start with - symbol"),
    param(".at","", id="cannot start with . symbol"),
    param("+at","", id="cannot start with + symbol"),
    param("*at","", id="cannot contain other symbol"),
])
def test_parser_catname(depvar, expected):
    r"""
    3.1.1 Category names

    A category name may contain any of the characters [A-Za-z0-9+_.-]. It
    must not begin with a hyphen, a dot or a plus sign.

    """
    parser = Parser(depvar)
    parser.cat_name()
    value = next((p.value for p in parser.parcels if p.kind=="CategoryName"), "")
    assert value == expected

@pytest.mark.parametrize("depvar,expected",[
    param("slot","", id="no colon"),
    param(":slot",":slot", id="default"),
    param(":slot/sub",":slot/sub", id="subslot"),
    param(":/sub",":/sub", id="primary slot not required"),
    param(":/",":/", id="empty slot/subslot"),
    param(":",":", id="empty slot"),
    param(":*",":*", id="* operator"),
    param(":=",":=", id="= operator"),
    param(":slot=",":slot=", id="= operator with slot name"),
    param(":-slot",":", id="cannot begin with -"),
    param(":.slot",":", id="cannot begin with ."),
    param(":+slot",":", id="cannot begin with +"),
    param(":_slot",":_slot", id="can begin with _"),
    param(":10slot",":10slot", id="can begin with numbers"),

])
def test_parser_slot(depvar, expected):
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
    parser = Parser(depvar)
    parser.slot()
    value = next((p.value for p in parser.parcels if p.kind=="Slot"), "")
    assert value == expected


@pytest.mark.parametrize("depvar,expected",[
    param("[use]","[use]", id="default"),
    param("[]","[]", id="empty"),
    param("[opt=]","[opt=]", id="equals operator"),
    param("[=]","", id="= operator alone is not allowed"),
    param("[!opt=]","[!opt=]", id="disabled option with ="),
    param("[opt?]","[opt?]", id="option with ?"),
    param("[!opt?]","[!opt?]", id="disabled option with ?"),
    param("[-opt]","[-opt]", id="disabled"),
    param("[!!opt]","", id="cannot start with two symbols"),
    param("[opt??]","", id="cannot end with two symbols"),
    param("[use,opt,opt=,!opt=,opt?,!opt?,-opt]","[use,opt,opt=,!opt=,opt?,!opt?,-opt]", id="multiple options allowed"),
    param("[use,]","", id="trailing comma not allowed"), # Really is it not allowed?
    param("[opt(+)]","[opt(+)]", id="basic option with default"),
    param("[!opt(+)?]","[!opt(+)?]", id="option with symbols and + default"),
    param("[!opt(-)?]","[!opt(-)?]", id="option with symbols and - default"),
    param("[!opt(+)(+)?]","", id="multiple defaults not allowed"),
    param("[!opt(++)?]","", id="multiple defaults not allowed"),
    param("[!opt?(+)]","", id="default must come before operator"),
    param("[opt!]","", id="! is not a valid suffix"),
])
def test_parser_usedependencies(depvar, expected):
    r"""
    8.3.4 2-style and 4-style USE dependencies

    A 2-style or 4-style use dependency consists of one of the following:
    - [opt] The flag must be enabled.
    - [opt=] The flag must be enabled if the flag is enabled for the package
      with the dependency, or disabled otherwise.
    - [!opt=] The flag must be disabled if the flag is enabled for the package
      with the dependency, or enabled otherwise.
    - [opt?] The flag must be enabled if the flag is enabled for the package
      with the dependency.
    - [!opt?] The flag must be disabled if the use flag is disabled for the
      package with the dependency.
    - [-opt] The flag must be disabled.

    Multiple requirements may be combined using commas, e. g.
    [first,-second,third?]. When multiple requirements are specified, all must
    match for a successful match. In a 4-style use dependency, the flag name
    may immediately be followed by a default specified by either (+) or (-).
    The former indicates that, when applying the use dependency to a package
    that does not have the flag in question in IUSE_REFERENCEABLE, the package
    manager shall behave as if the flag were present and enabled; the latter,
    present and disabled. Unless a 4-style default is specified, it is an error
    for a use dependency to be applied to an ebuild which does not have the
    flag in question in IUSE_REFERENCEABLE. Note: By extension of the above, a
    default that could reference an ebuild using an EAPI not supporting profile
    IUSE injections cannot rely upon any particular behaviour for flags that
    would not have to be part of IUSE. It is an error for an ebuild to use a
    conditional use dependency when that ebuild does not have the flag in
    IUSE_EFFECTIVE.

    """
    parser = Parser(depvar)
    parser.use_deps()
    value = next((p.value for p in parser.parcels if p.kind=="UseDependencies"), "")
    assert value == expected


@pytest.mark.parametrize("depvar,expected",[
    param(
        "!!>=c-t/pkg-1.22.333a_alpha1-r42:_slot/_sub[!opt?,opt,-use(+),use(-)=]",
        "!!>=c-t/pkg-1.22.333a_alpha1-r42:_slot/_sub[!opt?,opt,-use(+),use(-)=]", 
        id="complex example"),
])
def test_parser_atom(depvar, expected):
    parser = Parser(depvar)
    parser.atom()
    value = next((p.value for p in parser.parcels if p.kind=="Atom"), "")
    assert value == expected


@pytest.mark.parametrize("depvar,expected",[
    param("()","()", id="empty"),
    param("(atom)","(atom)", id="one without whitespace"),
    param("( atom )","( atom )", id="one with whitespace"),
    param("(atom pkg)","(atom pkg)", id="multiple"),
    param("(atom[-use(+)=] pkg-1.0[use(-)?])","(atom[-use(+)=] pkg-1.0[use(-)?])", id="complex atoms"),
])
def test_parser_allgroup(depvar, expected):
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
    parser = Parser(depvar)
    parser.all_of_group()
    value = next((p.value for p in parser.parcels if p.kind=="AllOfGroup"), "")
    assert value == expected

@pytest.mark.parametrize("depvar,expected",[
    param("|| ()","|| ()", id="empty"),
    param("| ()","", id="two | required"),
    param("|| (atom)","|| (atom)", id="one without whitespace"),
    param("|| ( atom )","|| ( atom )", id="one with whitespace"),
    param("|| (atom pkg)","|| (atom pkg)", id="multiple"),
    param("|| (atom[-use(+)=] pkg-1.0[use(-)?])","|| (atom[-use(+)=] pkg-1.0[use(-)?])", id="complex atoms"),
])
def test_parser_anygroup(depvar, expected):
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
    parser = Parser(depvar)
    parser.any_of_group()
    value = next((p.value for p in parser.parcels if p.kind=="AnyOfGroup"), "")
    assert value == expected

@pytest.mark.parametrize("depvar,expected",[
    param("^^ ()","^^ ()", id="empty"),
    param("^ ()","", id="two ^ required"),
    param("^^ (atom)","^^ (atom)", id="one without whitespace"),
    param("^^ ( atom )","^^ ( atom )", id="one with whitespace"),
    param("^^ (atom pkg)","^^ (atom pkg)", id="multiple"),
    param("^^ (atom[-use(+)=] pkg-1.0[use(-)?])","^^ (atom[-use(+)=] pkg-1.0[use(-)?])", id="complex atoms"),
])
def test_parser_onegroup(depvar, expected):
    r"""
    8.2 Dependency Specification Format

    An exactly-one-of group, which has the same format as the any-of group, but
    begins with the string ^^ instead. Permitted in REQUIRED_USE.

    # EXTRA NOTE: the whitespace requirement is not enforced by the parser
    # here. 

    """
    parser = Parser(depvar)
    parser.exactly_one_of_group()
    value = next((p.value for p in parser.parcels if p.kind=="ExactlyOneOfGroup"), "")
    assert value == expected

@pytest.mark.parametrize("depvar,expected",[
    param("?? ()","?? ()", id="empty"),
    param("? ()","", id="two ? required"),
    param("?? (atom)","?? (atom)", id="one without whitespace"),
    param("?? ( atom )","?? ( atom )", id="one with whitespace"),
    param("?? (atom pkg)","?? (atom pkg)", id="multiple"),
    param("?? (atom[-use(+)=] pkg-1.0[use(-)?])","?? (atom[-use(+)=] pkg-1.0[use(-)?])", id="complex atoms"),
])
def test_parser_mostonegroup(depvar, expected):
    r"""
    8.2 Dependency Specification Format

    An at-most-one-of group, which has the same format as the any-of group,
    but begins with the string ?? instead. Permitted in REQUIRED_USE in
    EAPIs listed in table 8.5 as supporting REQUIRED_USE ?? groups.

    # EXTRA NOTE: the whitespace requirement is not enforced by the parser
    # here. 

    """
    parser = Parser(depvar)
    parser.most_one_of_group()
    value = next((p.value for p in parser.parcels if p.kind=="MostOneOfGroup"), "")
    assert value == expected

@pytest.mark.parametrize("depvar,expected",[
    param("use? ()","use? ()", id="empty"),
    param("? ()","", id="use flag required"),
    param("use? (pkg)","use? (pkg)", id="one atom"),
    param("use? ( pkg    )","use? ( pkg    )", id="with whitespace"),
    param("use? (cat/pkg atom)","use? (cat/pkg atom)", id="multiple atoms"),
    param("use? (cat/pkg use2? (atom))","use? (cat/pkg use2? (atom))", id="nested use"),
])
def test_parser_dynamicuse(depvar, expected):
    r"""
    8.2 Dependency Specification Format

    A use-conditional group, which consists of an optional exclamation mark,
    followed by a use flag name, followed by a question mark, followed by
    whitespace, followed by an open parenthesis, followed by whitespace,
    followed by one or more of (a dependency item of any kind followed by
    whitespace), followed by a close parenthesis. More formally:
    use-conditional ::= ’!’? flag-name ’?’ whitespace ’(’ whitespace (item
    whitespace)+ ’)’. Permitted in all specification style variables.

    # EXTRA NOTE: the whitespace requirement is not enforced by the parser
    # here. 

    """
    parser = Parser(depvar)
    parser.dynamic_use()
    value = next(reversed(list(p.value for p in parser.parcels if p.kind=="DynamicUse")), "")
    assert value == expected
